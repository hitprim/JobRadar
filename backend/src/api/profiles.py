"""CRUD профилей.

Endpoints:
    GET    /api/profiles              — список активных профилей юзера
    POST   /api/profiles              — создать профиль (409 при превышении лимита)
    PATCH  /api/profiles/{id}         — обновить (без resume)
    PUT    /api/profiles/{id}/resume  — обновить резюме (отдельно из-за размера)
    GET    /api/profiles/{id}/resume  — получить расшифрованное резюме
    DELETE /api/profiles/{id}         — soft-delete (is_active=false)
    POST   /api/profiles/{id}/activate — сделать активным
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    ProfileCreateRequest,
    ProfilePublic,
    ProfileUpdateRequest,
    ResumeResponse,
    ResumeUpdateRequest,
)
from src.db.repositories import ProfileRepository, UserRepository
from src.db.session import get_session
from src.domain.profile import ProfileCreate, ProfileUpdate
from src.security.deps import CurrentUserId
from src.services.profile import (
    ProfileLimitReachedError,
    ProfileNotFoundError,
    ProfileService,
    ResumeTooLongError,
    UserNotFoundError,
)

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _service(session: AsyncSession) -> ProfileService:
    return ProfileService(ProfileRepository(session), UserRepository(session))


@router.get("", response_model=list[ProfilePublic])
async def list_profiles(session: SessionDep, user_id: CurrentUserId) -> list[ProfilePublic]:
    profiles = await _service(session).list_for_user(user_id)
    return [ProfilePublic.model_validate(p) for p in profiles]


@router.post(
    "",
    response_model=ProfilePublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_profile(
    body: ProfileCreateRequest,
    session: SessionDep,
    user_id: CurrentUserId,
) -> ProfilePublic:
    try:
        profile = await _service(session).create_for_user(
            user_id, ProfileCreate.model_validate(body.model_dump())
        )
    except ProfileLimitReachedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    await session.commit()
    return ProfilePublic.model_validate(profile)


@router.patch("/{profile_id}", response_model=ProfilePublic)
async def update_profile(
    profile_id: int,
    body: ProfileUpdateRequest,
    session: SessionDep,
    user_id: CurrentUserId,
) -> ProfilePublic:
    try:
        profile = await _service(session).update_for_user(
            profile_id,
            user_id,
            ProfileUpdate.model_validate(body.model_dump(exclude_unset=True)),
        )
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await session.commit()
    return ProfilePublic.model_validate(profile)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(profile_id: int, session: SessionDep, user_id: CurrentUserId) -> None:
    try:
        await _service(session).soft_delete_for_user(profile_id, user_id)
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await session.commit()


@router.post("/{profile_id}/activate", status_code=status.HTTP_204_NO_CONTENT)
async def activate_profile(profile_id: int, session: SessionDep, user_id: CurrentUserId) -> None:
    try:
        await _service(session).activate_for_user(profile_id, user_id)
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await session.commit()


@router.put("/{profile_id}/resume", status_code=status.HTTP_204_NO_CONTENT)
async def set_resume(
    profile_id: int,
    body: ResumeUpdateRequest,
    session: SessionDep,
    user_id: CurrentUserId,
) -> None:
    try:
        await _service(session).set_resume(profile_id, user_id, body.resume_text)
    except ResumeTooLongError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)
        ) from exc
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except UserNotFoundError as exc:  # pragma: no cover (только при гнилом JWT)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    await session.commit()


@router.get("/{profile_id}/resume", response_model=ResumeResponse)
async def get_resume(
    profile_id: int, session: SessionDep, user_id: CurrentUserId
) -> ResumeResponse:
    try:
        text = await _service(session).get_resume(profile_id, user_id)
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except UserNotFoundError as exc:  # pragma: no cover
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return ResumeResponse(resume_text=text)
