"""Repository для отзывов о компаниях + агрегаты respect-score.

company_key вычисляется в Python (domain.company_review.company_key_for) —
единый источник нормализации. Поэтому верификация «есть ли отклик к компании»
тоже считается в Python: тянем (company_id, company_name) откликов юзера и
сводим к множеству ключей.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.db.models import Application as ApplicationORM
from src.db.models import CompanyReview as CompanyReviewORM
from src.db.models import CompanyReviewReport as CompanyReviewReportORM
from src.db.models import Profile as ProfileORM
from src.db.models import Vacancy as VacancyORM
from src.db.repositories.base import BaseRepository
from src.domain.company_review import (
    CompanyReview,
    CompanyReviewSummary,
    company_key_for,
    compute_review_score,
)


def _to_domain(orm: CompanyReviewORM) -> CompanyReview:
    return CompanyReview(
        id=orm.id,
        company_key=orm.company_key,
        company_name=orm.company_name,
        user_id=orm.user_id,
        profile_id=orm.profile_id,
        responded=orm.responded,  # type: ignore[arg-type]
        respect=orm.respect,  # type: ignore[arg-type]
        feedback=orm.feedback,  # type: ignore[arg-type]
        honesty=orm.honesty,  # type: ignore[arg-type]
        process=orm.process,  # type: ignore[arg-type]
        text=orm.text,
        score=orm.score,
        is_hidden=orm.is_hidden,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


class CompanyReviewRepository(BaseRepository):
    async def get_my_review(self, company_key: str, user_id: int) -> CompanyReview | None:
        stmt = select(CompanyReviewORM).where(
            CompanyReviewORM.company_key == company_key,
            CompanyReviewORM.user_id == user_id,
        )
        orm = (await self.session.execute(stmt)).scalar_one_or_none()
        return _to_domain(orm) if orm else None

    async def list_for_key(
        self, company_key: str, *, limit: int = 50, offset: int = 0
    ) -> list[CompanyReview]:
        stmt = (
            select(CompanyReviewORM)
            .where(
                CompanyReviewORM.company_key == company_key,
                CompanyReviewORM.is_hidden.is_(False),
            )
            .order_by(CompanyReviewORM.created_at.desc(), CompanyReviewORM.id.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_to_domain(o) for o in rows]

    async def summary_for_key(self, company_key: str) -> CompanyReviewSummary:
        stmt = select(
            func.avg(CompanyReviewORM.score),
            func.count(CompanyReviewORM.id),
        ).where(
            CompanyReviewORM.company_key == company_key,
            CompanyReviewORM.is_hidden.is_(False),
        )
        avg_score, count = (await self.session.execute(stmt)).one()
        return CompanyReviewSummary(
            company_key=company_key,
            respect_score=round(float(avg_score)) if avg_score is not None else None,
            review_count=int(count),
        )

    async def summaries_for_keys(
        self, keys: list[str]
    ) -> dict[str, CompanyReviewSummary]:
        """Агрегаты для набора ключей одним запросом (для бейджей в ленте)."""
        if not keys:
            return {}
        stmt = (
            select(
                CompanyReviewORM.company_key,
                func.avg(CompanyReviewORM.score),
                func.count(CompanyReviewORM.id),
            )
            .where(
                CompanyReviewORM.company_key.in_(keys),
                CompanyReviewORM.is_hidden.is_(False),
            )
            .group_by(CompanyReviewORM.company_key)
        )
        out: dict[str, CompanyReviewSummary] = {}
        for key, avg_score, count in (await self.session.execute(stmt)).all():
            out[key] = CompanyReviewSummary(
                company_key=key,
                respect_score=round(float(avg_score)) if avg_score is not None else None,
                review_count=int(count),
            )
        return out

    async def get_by_id(self, review_id: int) -> CompanyReview | None:
        orm = await self.session.get(CompanyReviewORM, review_id)
        return _to_domain(orm) if orm else None

    async def add_report(self, review_id: int, user_id: int) -> int:
        """Регистрирует жалобу (идемпотентно по review_id+user_id) и возвращает
        число уникальных жалобщиков на этот отзыв."""
        insert_stmt = pg_insert(CompanyReviewReportORM).values(
            review_id=review_id, user_id=user_id
        )
        await self.session.execute(
            insert_stmt.on_conflict_do_nothing(
                constraint="uq_company_review_reports_review_user"
            )
        )
        count_stmt = select(func.count(CompanyReviewReportORM.id)).where(
            CompanyReviewReportORM.review_id == review_id
        )
        return int((await self.session.execute(count_stmt)).scalar_one())

    async def set_hidden(self, review_id: int, hidden: bool) -> None:
        orm = await self.session.get(CompanyReviewORM, review_id)
        if orm is not None:
            orm.is_hidden = hidden

    async def user_company_keys(self, user_id: int) -> set[str]:
        """Множество company_key компаний, к которым у юзера есть отклик.

        Используется для верификации права оставить отзыв (через трекер).
        """
        stmt = (
            select(VacancyORM.company_id, VacancyORM.company_name)
            .join(ApplicationORM, ApplicationORM.vacancy_id == VacancyORM.id)
            .join(ProfileORM, ProfileORM.id == ApplicationORM.profile_id)
            .where(ProfileORM.user_id == user_id)
            .distinct()
        )
        keys: set[str] = set()
        for company_id, company_name in (await self.session.execute(stmt)).all():
            key = company_key_for(company_id, company_name)
            if key is not None:
                keys.add(key)
        return keys

    async def upsert(
        self,
        *,
        company_key: str,
        company_name: str | None,
        user_id: int,
        profile_id: int | None,
        responded: str,
        respect: str,
        feedback: str,
        honesty: str,
        process: str,
        text: str | None,
    ) -> CompanyReview:
        """Создаёт/обновляет отзыв (уникальность по company_key+user_id)."""
        score = compute_review_score(
            responded,  # type: ignore[arg-type]
            respect,  # type: ignore[arg-type]
            feedback,  # type: ignore[arg-type]
            honesty,  # type: ignore[arg-type]
            process,  # type: ignore[arg-type]
        )
        values = {
            "company_key": company_key,
            "company_name": company_name,
            "user_id": user_id,
            "profile_id": profile_id,
            "responded": responded,
            "respect": respect,
            "feedback": feedback,
            "honesty": honesty,
            "process": process,
            "text": text,
            "score": score,
        }
        insert_stmt = pg_insert(CompanyReviewORM).values(values)
        stmt = insert_stmt.on_conflict_do_update(
            constraint="uq_company_reviews_company_user",
            set_={
                "company_name": insert_stmt.excluded.company_name,
                "profile_id": insert_stmt.excluded.profile_id,
                "responded": insert_stmt.excluded.responded,
                "respect": insert_stmt.excluded.respect,
                "feedback": insert_stmt.excluded.feedback,
                "honesty": insert_stmt.excluded.honesty,
                "process": insert_stmt.excluded.process,
                "text": insert_stmt.excluded.text,
                "score": insert_stmt.excluded.score,
                "updated_at": func.now(),
            },
        ).returning(CompanyReviewORM)
        orm = (await self.session.execute(stmt)).scalar_one()
        return _to_domain(orm)
