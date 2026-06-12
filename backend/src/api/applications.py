"""Applications API: трекер откликов.

Endpoints:
    GET    /api/profiles/{profile_id}/applications
    POST   /api/applications?profile_id=
    GET    /api/applications/{id}
    PATCH  /api/applications/{id}
    GET    /api/applications/{id}/history
    GET    /api/profiles/{profile_id}/funnel
"""

from __future__ import annotations

import csv
import io
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    ApplicationCreateRequest,
    ApplicationListItemPublic,
    ApplicationPatchRequest,
    ApplicationPublic,
    ApplicationStatusHistoryPublic,
    FunnelPublic,
)
from src.db.repositories import ApplicationRepository, ProfileRepository
from src.db.session import get_session
from src.domain.application import (
    ApplicationCreate,
    ApplicationStatus,
    ApplicationUpdate,
)
from src.security.deps import CurrentUserId
from src.services.application import (
    ApplicationNotFoundError,
    ApplicationService,
    DuplicateApplicationError,
    ProfileNotAccessibleError,
    VacancyNotFoundError,
)

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# Человекочитаемые статусы для CSV (совпадают с APPLICATION_STATUS_RU на фронте).
_STATUS_RU: dict[str, str] = {
    "sent": "Отправлено",
    "hr": "HR",
    "tech": "Тех. интервью",
    "final": "Финал",
    "offer": "Оффер",
    "reject": "Отказ",
}


def _service(session: AsyncSession) -> ApplicationService:
    return ApplicationService(ApplicationRepository(session), ProfileRepository(session))


@router.get(
    "/api/profiles/{profile_id}/applications",
    response_model=list[ApplicationListItemPublic],
    tags=["applications"],
)
async def list_applications(
    profile_id: int,
    session: SessionDep,
    user_id: CurrentUserId,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[ApplicationListItemPublic]:
    try:
        items = await _service(session).list_for_user_profile(
            profile_id, user_id, limit=limit, offset=offset
        )
    except ProfileNotAccessibleError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [ApplicationListItemPublic.model_validate(a) for a in items]


@router.get(
    "/api/profiles/{profile_id}/applications/export",
    tags=["applications"],
    summary="Экспорт трекера в CSV",
)
async def export_applications(
    profile_id: int, session: SessionDep, user_id: CurrentUserId
) -> Response:
    try:
        rows = await _service(session).export_for_user_profile(profile_id, user_id)
    except ProfileNotAccessibleError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["ID", "Статус", "Вакансия", "Компания", "Ссылка", "Заметки", "Создано", "Обновлено"]
    )
    for r in rows:
        writer.writerow(
            [
                r.application_id,
                _STATUS_RU.get(r.status, r.status),
                r.vacancy_title or "",
                r.company_name or "",
                r.vacancy_url or "",
                r.notes or "",
                r.created_at.isoformat(),
                r.updated_at.isoformat(),
            ]
        )

    # utf-8-sig (BOM) — чтобы Excel на Windows корректно открыл кириллицу.
    content = buf.getvalue().encode("utf-8-sig")
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="jobradar_tracker_{profile_id}.csv"'
        },
    )


@router.post(
    "/api/applications",
    response_model=ApplicationPublic,
    status_code=status.HTTP_201_CREATED,
    tags=["applications"],
)
async def create_application(
    body: ApplicationCreateRequest,
    session: SessionDep,
    user_id: CurrentUserId,
    profile_id: int = Query(..., description="ID профиля, от имени которого создаём отклик"),
) -> ApplicationPublic:
    try:
        app = await _service(session).create_for_user(
            profile_id,
            user_id,
            ApplicationCreate.model_validate(body.model_dump()),
        )
    except ProfileNotAccessibleError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VacancyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DuplicateApplicationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
            headers={"X-Existing-Application-Id": str(exc.existing_id)},
        ) from exc
    await session.commit()
    return ApplicationPublic.model_validate(app)


@router.get(
    "/api/applications/{application_id}",
    response_model=ApplicationPublic,
    tags=["applications"],
)
async def get_application(
    application_id: int, session: SessionDep, user_id: CurrentUserId
) -> ApplicationPublic:
    try:
        app = await _service(session).get_for_user(application_id, user_id)
    except ApplicationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApplicationPublic.model_validate(app)


@router.patch(
    "/api/applications/{application_id}",
    response_model=ApplicationPublic,
    tags=["applications"],
)
async def patch_application(
    application_id: int,
    body: ApplicationPatchRequest,
    session: SessionDep,
    user_id: CurrentUserId,
) -> ApplicationPublic:
    patch = body.model_dump(exclude_unset=True)
    # status в DTO — str (pattern), внутренний контракт — Literal. Каст безопасен:
    # схема уже отвалидировала множество.
    if "status" in patch and patch["status"] is not None:
        patch["status"] = cast(ApplicationStatus, patch["status"])
    try:
        app = await _service(session).update_for_user(
            application_id, user_id, ApplicationUpdate.model_validate(patch)
        )
    except ApplicationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return ApplicationPublic.model_validate(app)


@router.get(
    "/api/applications/{application_id}/history",
    response_model=list[ApplicationStatusHistoryPublic],
    tags=["applications"],
)
async def get_application_history(
    application_id: int, session: SessionDep, user_id: CurrentUserId
) -> list[ApplicationStatusHistoryPublic]:
    try:
        history = await _service(session).list_history_for_user(application_id, user_id)
    except ApplicationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [ApplicationStatusHistoryPublic.model_validate(h) for h in history]


@router.get(
    "/api/profiles/{profile_id}/funnel",
    response_model=FunnelPublic,
    tags=["applications"],
)
async def get_funnel(profile_id: int, session: SessionDep, user_id: CurrentUserId) -> FunnelPublic:
    try:
        funnel = await _service(session).funnel_for_user_profile(profile_id, user_id)
    except ProfileNotAccessibleError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FunnelPublic.model_validate(funnel.model_dump())
