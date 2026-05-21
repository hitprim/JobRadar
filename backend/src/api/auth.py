"""Telegram WebApp авторизация.

POST /api/auth/telegram — принимает initData, валидирует HMAC, выдаёт JWT.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import TelegramAuthRequest, TelegramAuthResponse, UserPublic
from src.config import settings
from src.db.repositories import UserRepository
from src.db.session import get_session
from src.security.jwt import encode_access_token
from src.security.telegram_auth import (
    InitDataError,
    InitDataExpiredError,
    InvalidInitDataSignatureError,
    MalformedInitDataError,
    validate_init_data,
)
from src.services.user import UserService

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post(
    "/telegram",
    response_model=TelegramAuthResponse,
    summary="Авторизация через Telegram WebApp initData",
)
async def telegram_login(body: TelegramAuthRequest, session: SessionDep) -> TelegramAuthResponse:
    try:
        validated = validate_init_data(body.init_data)
    except InvalidInitDataSignatureError as exc:
        logger.warning("telegram auth: signature mismatch")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid initData signature",
        ) from exc
    except InitDataExpiredError as exc:
        logger.bind(reason=str(exc)).warning("telegram auth: expired initData")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="initData expired",
        ) from exc
    except MalformedInitDataError as exc:
        logger.bind(reason=str(exc)).warning("telegram auth: malformed initData")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"malformed initData: {exc}",
        ) from exc
    except InitDataError as exc:  # pragma: no cover (safety net)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    users_repo = UserRepository(session)
    service = UserService(users_repo)
    result = await service.upsert_from_telegram(validated.user)
    await session.commit()

    token = encode_access_token(user_id=result.user.id, telegram_id=result.user.telegram_id)

    logger.bind(
        user_id=result.user.id,
        telegram_id=result.user.telegram_id,
        is_new=result.created,
    ).info("telegram auth ok")

    return TelegramAuthResponse(
        access_token=token,
        expires_in=settings.jwt_ttl_minutes * 60,
        user=UserPublic.model_validate(result.user),
        is_new_user=result.created,
    )
