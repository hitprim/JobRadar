"""Sources CRUD + ручной refresh.

Endpoints:
    GET    /api/profiles/{profile_id}/sources
    POST   /api/profiles/{profile_id}/sources
    DELETE /api/sources/{source_id}
    POST   /api/sources/{source_id}/refresh
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    ParseResultPublic,
    SourceCreateRequest,
    SourcePublic,
)
from src.db.repositories import (
    ProfileRepository,
    SourceRepository,
    VacancyRepository,
)
from src.db.session import get_session
from src.domain.source import SourceCreate
from src.security.deps import CurrentUserId
from src.services.parser import (
    ParserService,
    SourceNotFoundError,
    UnsupportedSourceTypeError,
)

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


@router.post(
    "/api/sources/{source_id}/refresh",
    response_model=ParseResultPublic,
    tags=["sources"],
)
async def refresh_source(
    source_id: int, session: SessionDep, user_id: CurrentUserId
) -> ParseResultPublic:
    parser = ParserService(_sources(session), _profiles(session), VacancyRepository(session))
    try:
        result = await parser.parse_for_user(source_id, user_id)
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UnsupportedSourceTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return ParseResultPublic.model_validate(result.model_dump())
