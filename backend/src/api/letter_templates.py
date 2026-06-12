"""Letter templates API: сохранённые шаблоны сопроводительных.

Endpoints:
    GET    /api/profiles/{profile_id}/letter-templates  — список шаблонов профиля
    POST   /api/profiles/{profile_id}/letter-templates  — создать
    PATCH  /api/letter-templates/{template_id}          — обновить
    DELETE /api/letter-templates/{template_id}          — удалить
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    LetterTemplateCreateRequest,
    LetterTemplatePatchRequest,
    LetterTemplatePublic,
)
from src.db.repositories import LetterTemplateRepository, ProfileRepository
from src.db.session import get_session
from src.security.deps import CurrentUserId
from src.services.letter_template import (
    LetterTemplateService,
    ProfileNotAccessibleError,
    TemplateNotFoundError,
)

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _service(session: AsyncSession) -> LetterTemplateService:
    return LetterTemplateService(
        LetterTemplateRepository(session), ProfileRepository(session)
    )


@router.get(
    "/api/profiles/{profile_id}/letter-templates",
    response_model=list[LetterTemplatePublic],
    tags=["letters"],
)
async def list_templates(
    profile_id: int, session: SessionDep, user_id: CurrentUserId
) -> list[LetterTemplatePublic]:
    try:
        items = await _service(session).list_for_profile(profile_id, user_id)
    except ProfileNotAccessibleError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [LetterTemplatePublic.model_validate(i) for i in items]


@router.post(
    "/api/profiles/{profile_id}/letter-templates",
    response_model=LetterTemplatePublic,
    status_code=status.HTTP_201_CREATED,
    tags=["letters"],
)
async def create_template(
    profile_id: int,
    body: LetterTemplateCreateRequest,
    session: SessionDep,
    user_id: CurrentUserId,
) -> LetterTemplatePublic:
    try:
        tpl = await _service(session).create(
            profile_id, user_id, title=body.title, body=body.body
        )
    except ProfileNotAccessibleError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return LetterTemplatePublic.model_validate(tpl)


@router.patch(
    "/api/letter-templates/{template_id}",
    response_model=LetterTemplatePublic,
    tags=["letters"],
)
async def update_template(
    template_id: int,
    body: LetterTemplatePatchRequest,
    session: SessionDep,
    user_id: CurrentUserId,
) -> LetterTemplatePublic:
    try:
        tpl = await _service(session).update(
            template_id, user_id, title=body.title, body=body.body
        )
    except TemplateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return LetterTemplatePublic.model_validate(tpl)


@router.delete(
    "/api/letter-templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["letters"],
)
async def delete_template(
    template_id: int, session: SessionDep, user_id: CurrentUserId
) -> None:
    try:
        await _service(session).delete(template_id, user_id)
    except TemplateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
