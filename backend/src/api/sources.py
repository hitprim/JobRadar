"""Sources CRUD + ручной refresh.

Endpoints:
    GET    /api/profiles/{profile_id}/sources
    POST   /api/profiles/{profile_id}/sources
    DELETE /api/sources/{source_id}
    POST   /api/sources/{source_id}/refresh
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    RefreshAcceptedPublic,
    SourceCreateRequest,
    SourcePublic,
)
from src.db.repositories import (
    ProfileRepository,
    SourceRepository,
    VacancyRepository,
)
from src.db.session import SessionMaker, get_session
from src.domain.source import SourceCreate
from src.security.deps import CurrentUserId
from src.services.notifications import NotificationsService
from src.services.parser import ParserService

# Один router отвечает за оба префикса. Подключаем в main через include_router без префикса.
router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _sources(session: AsyncSession) -> SourceRepository:
    return SourceRepository(session)


def _profiles(session: AsyncSession) -> ProfileRepository:
    return ProfileRepository(session)


@router.get(
    "/api/profiles/{profile_id}/sources",
    response_model=list[SourcePublic],
    tags=["sources"],
)
async def list_sources(
    profile_id: int, session: SessionDep, user_id: CurrentUserId
) -> list[SourcePublic]:
    # Защита от IDOR: profile должен принадлежать юзеру
    profile = await _profiles(session).get_by_id_for_user(profile_id, user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="profile not found")
    items = await _sources(session).list_for_profile(profile_id)
    return [SourcePublic.model_validate(s) for s in items]


@router.post(
    "/api/profiles/{profile_id}/sources",
    response_model=SourcePublic,
    status_code=status.HTTP_201_CREATED,
    tags=["sources"],
)
async def create_source(
    profile_id: int,
    body: SourceCreateRequest,
    session: SessionDep,
    user_id: CurrentUserId,
) -> SourcePublic:
    profile = await _profiles(session).get_by_id_for_user(profile_id, user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="profile not found")
    if body.type != "hh":
        raise HTTPException(
            status_code=400,
            detail="only 'hh' source type is supported in v0.1",
        )
    # body.type validated above — это безопасный narrow для Literal-типа
    created = await _sources(session).create(
        profile_id, SourceCreate(type="hh", search_params=body.search_params)
    )
    await session.commit()
    return SourcePublic.model_validate(created)


@router.delete(
    "/api/sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["sources"],
)
async def delete_source(source_id: int, session: SessionDep, user_id: CurrentUserId) -> None:
    ok = await _sources(session).delete_for_user(source_id, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="source not found")
    await session.commit()


async def _run_refresh_background(source_id: int, user_id: int) -> None:
    """Фоновый прогон парсинга: своя сессия (request-сессия уже закрыта),
    свой commit, плюс пуш юзеру с итогом. Исключения не должны течь наружу —
    background task без обработчика молча проглотился бы, поэтому логируем сами.
    """
    async with SessionMaker() as session:
        notifier = NotificationsService(session)
        try:
            parser = ParserService(
                SourceRepository(session),
                ProfileRepository(session),
                VacancyRepository(session),
            )
            result = await parser.parse_for_user(source_id, user_id)
            await session.commit()
            await notifier.send_parse_result(
                user_id,
                inserted=result.inserted,
                status=result.status,
                error=result.error,
            )
        except Exception as exc:  # noqa: BLE001 — фон не должен падать молча
            await session.rollback()
            logger.bind(source_id=source_id, user_id=user_id).exception(
                "refresh: background parse failed: {}", exc
            )
            await notifier.send_parse_result(
                user_id, inserted=0, status="error", error=str(exc)
            )
        finally:
            await notifier.aclose()


@router.post(
    "/api/sources/{source_id}/refresh",
    response_model=RefreshAcceptedPublic,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["sources"],
)
async def refresh_source(
    source_id: int,
    session: SessionDep,
    user_id: CurrentUserId,
    background_tasks: BackgroundTasks,
) -> RefreshAcceptedPublic:
    """Запускает парсинг в фоне и сразу возвращает 202.

    Парсинг hh.ru через headless-Chrome занимает десятки секунд — держать на это
    время HTTP-запрос плохо (таймауты прокси/ngrok, зависший спиннер). Поэтому
    проверяем владение синхронно, а сам парсинг уносим в background task с
    пушем-итогом в Telegram.
    """
    # Проверка владения здесь (на request-сессии) → честный 404 до фона.
    source = await _sources(session).get_by_id_for_user(source_id, user_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"source {source_id} not found")
    if source.type != "hh":
        raise HTTPException(
            status_code=400, detail="only 'hh' source type is supported in v0.1"
        )

    background_tasks.add_task(_run_refresh_background, source_id, user_id)
    return RefreshAcceptedPublic(source_id=source_id)
