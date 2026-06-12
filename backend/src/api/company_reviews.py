"""Company reviews API: отзывы о компаниях (об отношении к соискателям).

Endpoints:
    GET  /api/vacancies/{vacancy_id}/company-review
    POST /api/vacancies/{vacancy_id}/company-review?profile_id=
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    CompanyReviewCreateRequest,
    CompanyReviewPublic,
    CompanyReviewReportResponse,
    CompanyReviewViewPublic,
)
from src.db.repositories import CompanyReviewRepository, VacancyRepository
from src.db.session import get_session
from src.domain.company_review import CompanyReview, CompanyReviewCreate, CompanyReviewView
from src.security.deps import CurrentUserId
from src.services.company_review import (
    CompanyNotIdentifiableError,
    CompanyReviewService,
    NotVerifiedError,
    ReviewNotFoundError,
    VacancyNotFoundError,
)

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _service(session: AsyncSession) -> CompanyReviewService:
    return CompanyReviewService(CompanyReviewRepository(session), VacancyRepository(session))


def _review_public(r: CompanyReview) -> CompanyReviewPublic:
    return CompanyReviewPublic.model_validate(r)


def _view_public(view: CompanyReviewView) -> CompanyReviewViewPublic:
    return CompanyReviewViewPublic(
        company_key=view.company_key,
        company_name=view.company_name,
        respect_score=view.respect_score,
        review_count=view.review_count,
        can_review=view.can_review,
        my_review=_review_public(view.my_review) if view.my_review else None,
        reviews=[_review_public(r) for r in view.reviews],
    )


@router.get(
    "/api/vacancies/{vacancy_id}/company-review",
    response_model=CompanyReviewViewPublic,
    tags=["company-reviews"],
)
async def get_company_review(
    vacancy_id: int, session: SessionDep, user_id: CurrentUserId
) -> CompanyReviewViewPublic:
    try:
        view = await _service(session).view_for_vacancy(vacancy_id, user_id)
    except VacancyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _view_public(view)


@router.post(
    "/api/vacancies/{vacancy_id}/company-review",
    response_model=CompanyReviewViewPublic,
    tags=["company-reviews"],
)
async def submit_company_review(
    vacancy_id: int,
    body: CompanyReviewCreateRequest,
    session: SessionDep,
    user_id: CurrentUserId,
    profile_id: int | None = Query(
        default=None, description="Активный профиль, в контексте которого оставлен отзыв"
    ),
) -> CompanyReviewViewPublic:
    try:
        view = await _service(session).submit_for_vacancy(
            vacancy_id,
            user_id,
            profile_id,
            CompanyReviewCreate.model_validate(body.model_dump()),
        )
    except VacancyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CompanyNotIdentifiableError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except NotVerifiedError as exc:
        # 403 — у юзера нет отклика к компании (нельзя оставить отзыв).
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    await session.commit()
    return _view_public(view)


@router.post(
    "/api/company-reviews/{review_id}/report",
    response_model=CompanyReviewReportResponse,
    tags=["company-reviews"],
)
async def report_company_review(
    review_id: int, session: SessionDep, user_id: CurrentUserId
) -> CompanyReviewReportResponse:
    """Пожаловаться на отзыв. При накоплении жалоб отзыв авто-скрывается."""
    try:
        count, hidden = await _service(session).report(review_id, user_id)
    except ReviewNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return CompanyReviewReportResponse(report_count=count, hidden=hidden)
