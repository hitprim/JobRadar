"""Vacancies + Feed.

Endpoints:
    GET  /api/profiles/{profile_id}/feed?limit=&offset=
    GET  /api/vacancies/{vacancy_id}
    POST /api/vacancies/{vacancy_id}/reaction
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    FeedItemPublic,
    ReactionRequest,
    VacancyPublic,
    VacancyReactionPublic,
)
from src.db.repositories import (
    ProfileRepository,
    ReactionRepository,
    VacancyRepository,
)
from src.db.session import get_session
from src.security.deps import CurrentUserId
from src.sources.base import SourceError
from src.sources.hh import HhSource

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get(
    "/api/profiles/{profile_id}/feed",
    response_model=list[FeedItemPublic],
    tags=["vacancies"],
)
async def get_feed(
    profile_id: int,
    session: SessionDep,
    user_id: CurrentUserId,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[FeedItemPublic]:
    profile = await ProfileRepository(session).get_by_id_for_user(profile_id, user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="profile not found")
    items = await VacancyRepository(session).list_feed_for_profile(
        profile_id, limit=limit, offset=offset
    )
    return [FeedItemPublic.model_validate(i.model_dump()) for i in items]


@router.get(
    "/api/vacancies/{vacancy_id}",
    response_model=VacancyPublic,
    tags=["vacancies"],
)
async def get_vacancy(
    vacancy_id: int,
    session: SessionDep,
    user_id: CurrentUserId,  # noqa: ARG001 — авторизация
) -> VacancyPublic:
    """Детали вакансии. Если description пуст — пытаемся загрузить через
    hh.ru on-demand (lazy fetch_details). Сетевые ошибки игнорируем
    (отдаём то, что есть)."""
    repo = VacancyRepository(session)
    vacancy = await repo.get_by_id(vacancy_id)
    if vacancy is None:
        raise HTTPException(status_code=404, detail="vacancy not found")

    if vacancy.description is None and vacancy.source_type == "hh":
        try:
            details = await HhSource().fetch_details(vacancy.external_id)
        except SourceError as exc:
            logger.bind(vacancy_id=vacancy_id, error=str(exc)).warning("lazy fetch_details failed")
            details = None
        if details is not None:
            description = details.get("description")
            skills = details.get("key_skills") or []
            skills_list = [s["name"] for s in skills if isinstance(s, dict) and "name" in s]
            await repo.update_details(vacancy_id, description=description, key_skills=skills_list)
            await session.commit()
            refreshed = await repo.get_by_id(vacancy_id)
            assert refreshed is not None
            vacancy = refreshed
    return VacancyPublic.model_validate(vacancy)


@router.post(
    "/api/vacancies/{vacancy_id}/reaction",
    response_model=VacancyReactionPublic,
    status_code=status.HTTP_200_OK,
    tags=["vacancies"],
)
async def react_to_vacancy(
    vacancy_id: int,
    body: ReactionRequest,
    session: SessionDep,
    user_id: CurrentUserId,
    profile_id: int = Query(..., description="ID профиля, от имени которого ставится реакция"),
) -> VacancyReactionPublic:
    reactions = ReactionRepository(session)
    if not await reactions.profile_belongs_to_user(profile_id, user_id):
        raise HTTPException(status_code=404, detail="profile not found")
    if not await reactions.vacancy_exists(vacancy_id):
        raise HTTPException(status_code=404, detail="vacancy not found")
    saved = await reactions.upsert_reaction(
        profile_id=profile_id, vacancy_id=vacancy_id, reaction=body.reaction
    )
    await session.commit()
    return VacancyReactionPublic.model_validate(saved)
