"""Letters API: генерация и редактирование сопроводительных.

Endpoints:
    POST   /api/vacancies/{vacancy_id}/letter?profile_id=  — сгенерировать новое
    GET    /api/letters/{letter_id}                        — получить
    PATCH  /api/letters/{letter_id}                        — редактировать
    GET    /api/profiles/{profile_id}/letters              — список писем профиля
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    LetterGenerateRequest,
    LetterGenerateResponse,
    LetterPatchRequest,
    LetterPublic,
)
from src.db.repositories import (
    LetterRepository,
    ProfileRepository,
    UserRepository,
    VacancyRepository,
)
from src.db.session import get_session
from src.llm import LLMError, LLMProvider, get_llm_provider
from src.security.deps import CurrentUserId
from src.services.letter import (
    ExtraInstructionsTooLongError,
    LetterNotFoundError,
    LetterService,
    ProfileNotAccessibleError,
    VacancyNotFoundError,
)

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]
LLMDep = Annotated[LLMProvider, Depends(get_llm_provider)]


def _service(session: AsyncSession, llm: LLMProvider) -> LetterService:
    return LetterService(
        llm,
        letters=LetterRepository(session),
        profiles=ProfileRepository(session),
        vacancies=VacancyRepository(session),
        users=UserRepository(session),
    )


@router.post(
    "/api/vacancies/{vacancy_id}/letter",
    response_model=LetterGenerateResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["letters"],
)
async def generate_letter(
    vacancy_id: int,
    body: LetterGenerateRequest,
    session: SessionDep,
    user_id: CurrentUserId,
    llm: LLMDep,
    profile_id: int = Query(..., description="ID профиля, для которого генерируем"),
) -> LetterGenerateResponse:
    service = _service(session, llm)
    try:
        result, letter = await service.generate(
            vacancy_id=vacancy_id,
            profile_id=profile_id,
            user_id=user_id,
            extra_instructions=body.extra_instructions,
        )
    except ProfileNotAccessibleError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VacancyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ExtraInstructionsTooLongError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except LLMError as exc:
        logger.bind(error=str(exc)).error("letter: LLM failure")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM provider error: {exc}",
        ) from exc

    await session.commit()
    return LetterGenerateResponse(
        letter=LetterPublic.model_validate(letter),
        draft_notes=result.draft_notes,
    )


@router.get(
    "/api/letters/{letter_id}",
    response_model=LetterPublic,
    tags=["letters"],
)
async def get_letter(
    letter_id: int, session: SessionDep, user_id: CurrentUserId, llm: LLMDep
) -> LetterPublic:
    try:
        letter = await _service(session, llm).get_for_user(letter_id, user_id)
    except LetterNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return LetterPublic.model_validate(letter)


@router.patch(
    "/api/letters/{letter_id}",
    response_model=LetterPublic,
    tags=["letters"],
)
async def patch_letter(
    letter_id: int,
    body: LetterPatchRequest,
    session: SessionDep,
    user_id: CurrentUserId,
    llm: LLMDep,
) -> LetterPublic:
    try:
        letter = await _service(session, llm).update_for_user(
            letter_id,
            user_id,
            text=body.text,
            used_in_application=body.used_in_application,
        )
    except LetterNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return LetterPublic.model_validate(letter)


@router.get(
    "/api/profiles/{profile_id}/letters",
    response_model=list[LetterPublic],
    tags=["letters"],
)
async def list_letters(
    profile_id: int,
    session: SessionDep,
    user_id: CurrentUserId,
    llm: LLMDep,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[LetterPublic]:
    try:
        items = await _service(session, llm).list_for_user_profile(
            profile_id, user_id, limit=limit, offset=offset
        )
    except ProfileNotAccessibleError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [LetterPublic.model_validate(i) for i in items]
