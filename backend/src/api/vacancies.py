"""Vacancies + Feed + Scoring.

Endpoints:
    GET  /api/profiles/{profile_id}/feed?limit=&offset=
    GET  /api/vacancies/{vacancy_id}
    POST /api/vacancies/{vacancy_id}/reaction
    POST /api/vacancies/{vacancy_id}/score?profile_id=&force=
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    CompanyReviewSummaryPublic,
    FeedItemPublic,
    ReactionRequest,
    ScoreResponse,
    VacancyPublic,
    VacancyReactionPublic,
)
from src.db.repositories import (
    CompanyReviewRepository,
    ProfileRepository,
    ReactionRepository,
    UserRepository,
    VacancyRepository,
)
from src.db.session import SessionMaker, get_session
from src.domain.company_review import company_key_for
from src.llm import LLMError, LLMProvider, get_llm_provider
from src.security.deps import CurrentUserId
from src.services.parser import get_source_impl
from src.services.scoring import (
    ProfileNotAccessibleError,
    ScoringService,
    VacancyNotFoundError,
)
from src.sources.base import SourceError

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# vacancy_id, для которых прямо сейчас идёт фоновая подгрузка деталей —
# чтобы повторные опросы клиента не плодили параллельные запуски Chrome.
_details_in_progress: set[int] = set()


async def _fetch_details_background(vacancy_id: int) -> None:
    """Фоновая подгрузка описания/навыков со страницы /vacancy/{id} через Chrome.

    Раньше это делалось синхронно прямо в GET — Chrome рендерит SPA hh.ru ~45-75с,
    а клиент отваливался по таймауту (axios 30с). Теперь GET возвращается сразу с
    description_pending=true, а описание дописывается здесь; клиент опрашивает
    эндпоинт повторно. Своя сессия (request-сессия уже закрыта). Исключения не
    должны течь из background task — логируем сами.
    """
    try:
        async with SessionMaker() as session:
            repo = VacancyRepository(session)
            vacancy = await repo.get_by_id(vacancy_id)
            if vacancy is None or vacancy.description is not None:
                return
            try:
                details = await get_source_impl(vacancy.source_type).fetch_details(
                    vacancy.external_id
                )
            except SourceError as exc:
                # Транзиентная сетевая ошибка/челлендж — НЕ помечаем attempted,
                # чтобы при следующем открытии можно было попробовать снова.
                logger.bind(vacancy_id=vacancy_id, error=str(exc)).warning(
                    "background fetch_details failed"
                )
                return
            description = details.get("description") if details else None
            skills = (details or {}).get("key_skills") or []
            skills_list = [s["name"] for s in skills if isinstance(s, dict) and "name" in s]
            # mark_attempted=True даже если описания нет — вакансия может быть в
            # архиве; не дёргаем Chrome повторно на каждый просмотр.
            await repo.update_details(
                vacancy_id,
                description=description,
                key_skills=skills_list,
                mark_attempted=True,
            )
            await session.commit()
    except Exception as exc:  # noqa: BLE001 — фон не должен падать молча
        logger.bind(vacancy_id=vacancy_id).exception(
            "background fetch_details crashed: {}", exc
        )
    finally:
        _details_in_progress.discard(vacancy_id)


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
    reaction: str | None = Query(
        default=None,
        pattern="^(like|save|skip|all)$",
        description=(
            "Фильтр ленты по реакции. Без значения — «Все» (скрыты пропущенные); "
            "like/save/skip — только с этой реакцией; all — всё, включая пропущенные."
        ),
    ),
) -> list[FeedItemPublic]:
    profile = await ProfileRepository(session).get_by_id_for_user(profile_id, user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="profile not found")
    items = await VacancyRepository(session).list_feed_for_profile(
        profile_id, limit=limit, offset=offset, reaction=reaction
    )

    # Бейдж respect-score: один агрегатный запрос по company_key всех вакансий
    # ленты (ключи считаем в Python — единый источник нормализации).
    keys_by_vacancy: dict[int, str] = {}
    for it in items:
        key = company_key_for(it.vacancy.company_id, it.vacancy.company_name)
        if key is not None:
            keys_by_vacancy[it.vacancy.id] = key
    summaries = await CompanyReviewRepository(session).summaries_for_keys(
        list(set(keys_by_vacancy.values()))
    )

    result: list[FeedItemPublic] = []
    for it in items:
        public = FeedItemPublic.model_validate(it.model_dump())
        key = keys_by_vacancy.get(it.vacancy.id)
        summary = summaries.get(key) if key else None
        if summary is not None and summary.review_count > 0:
            public.company_review = CompanyReviewSummaryPublic(
                respect_score=summary.respect_score,
                review_count=summary.review_count,
            )
        result.append(public)
    return result


@router.get(
    "/api/vacancies/{vacancy_id}",
    response_model=VacancyPublic,
    tags=["vacancies"],
)
async def get_vacancy(
    vacancy_id: int,
    session: SessionDep,
    user_id: CurrentUserId,  # noqa: ARG001 — авторизация
    background_tasks: BackgroundTasks,
) -> VacancyPublic:
    """Детали вакансии. Если description пуст — запускаем фоновую подгрузку с
    hh.ru (Chrome) и сразу возвращаем description_pending=true. Клиент опрашивает
    эндпоинт повторно, пока описание не появится. Так запрос не висит ~минуту и
    не отваливается по таймауту."""
    repo = VacancyRepository(session)
    vacancy = await repo.get_by_id(vacancy_id)
    if vacancy is None:
        raise HTTPException(status_code=404, detail="vacancy not found")

    description_pending = False
    if (
        vacancy.description is None
        and vacancy.source_type == "hh"
        and not await repo.was_details_attempted(vacancy_id)
    ):
        description_pending = True
        # Не плодим параллельные Chrome на повторных опросах того же клиента.
        if vacancy_id not in _details_in_progress:
            _details_in_progress.add(vacancy_id)
            background_tasks.add_task(_fetch_details_background, vacancy_id)

    result = VacancyPublic.model_validate(vacancy)
    result.description_pending = description_pending
    return result


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


@router.post(
    "/api/vacancies/{vacancy_id}/score",
    response_model=ScoreResponse,
    tags=["vacancies"],
)
async def score_vacancy(
    vacancy_id: int,
    session: SessionDep,
    user_id: CurrentUserId,
    llm: Annotated[LLMProvider, Depends(get_llm_provider)],
    profile_id: int = Query(..., description="ID профиля, для которого оцениваем"),
    force: bool = Query(False, description="Перескорить даже если score уже в кэше"),
) -> ScoreResponse:
    service = ScoringService(
        llm,
        profiles=ProfileRepository(session),
        vacancies=VacancyRepository(session),
        reactions=ReactionRepository(session),
        users=UserRepository(session),
    )
    try:
        result, _reaction, used_cache = await service.score_vacancy(
            vacancy_id=vacancy_id,
            profile_id=profile_id,
            user_id=user_id,
            force=force,
        )
    except ProfileNotAccessibleError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VacancyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LLMError as exc:
        logger.bind(error=str(exc)).error("scoring: LLM failure")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM provider error: {exc}",
        ) from exc

    # При cache-hit БД не менялась, но commit безопасен (no-op).
    if not used_cache:
        await session.commit()

    return ScoreResponse(
        score=result.score,
        reason=result.reason,
        red_flags=result.red_flags,
        green_flags=result.green_flags,
        from_cache=used_cache,
    )
