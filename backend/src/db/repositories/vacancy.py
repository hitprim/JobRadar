"""Repository для vacancies + feed-запросы.

UPSERT по (source_type, external_id) — дедупликация при повторном парсинге.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.db.models import Source as SourceORM
from src.db.models import SourceVacancy as SourceVacancyORM
from src.db.models import Vacancy as VacancyORM
from src.db.models import VacancyReaction as ReactionORM
from src.db.repositories.base import BaseRepository
from src.domain.vacancy import FeedItem, ParsedVacancy, Vacancy
from src.domain.vacancy import VacancyReaction as ReactionDomain


def _to_domain(orm: VacancyORM) -> Vacancy:
    return Vacancy(
        id=orm.id,
        external_id=orm.external_id,
        source_type=orm.source_type,
        title=orm.title,
        company_name=orm.company_name,
        company_id=orm.company_id,
        salary_from=orm.salary_from,
        salary_to=orm.salary_to,
        salary_currency=orm.salary_currency,
        url=orm.url,
        area_name=orm.area_name,
        schedule=orm.schedule,
        experience=orm.experience,
        description=orm.description,
        key_skills=list(orm.key_skills or []),
        published_at=orm.published_at,
        parsed_at=orm.parsed_at,
    )


def _reaction_to_domain(orm: ReactionORM) -> ReactionDomain:
    return ReactionDomain(
        id=orm.id,
        profile_id=orm.profile_id,
        vacancy_id=orm.vacancy_id,
        reaction=orm.reaction,
        score=orm.score,
        score_reason=orm.score_reason,
        red_flags=list(orm.red_flags or []),
        scored_at=orm.scored_at,
    )


class VacancyRepository(BaseRepository):
    async def get_by_id(self, vacancy_id: int) -> Vacancy | None:
        orm = await self.session.get(VacancyORM, vacancy_id)
        return _to_domain(orm) if orm else None

    async def get_by_external(self, source_type: str, external_id: str) -> Vacancy | None:
        stmt = select(VacancyORM).where(
            VacancyORM.source_type == source_type,
            VacancyORM.external_id == external_id,
        )
        orm = (await self.session.execute(stmt)).scalar_one_or_none()
        return _to_domain(orm) if orm else None

    async def upsert_many(self, items: list[ParsedVacancy]) -> tuple[int, int]:
        """UPSERT по (source_type, external_id).

        Возвращает (inserted, updated). Грубая оценка: считаем что если запись
        существовала — это update. Для точного подсчёта используем pre-check.
        """
        if not items:
            return 0, 0

        # Pre-check: какие external_id уже есть
        externals_by_source: dict[str, list[str]] = {}
        for it in items:
            externals_by_source.setdefault(it.source_type, []).append(it.external_id)

        existing_keys: set[tuple[str, str]] = set()
        for src_type, ext_ids in externals_by_source.items():
            sel_stmt = select(VacancyORM.source_type, VacancyORM.external_id).where(
                VacancyORM.source_type == src_type,
                VacancyORM.external_id.in_(ext_ids),
            )
            for row in (await self.session.execute(sel_stmt)).all():
                existing_keys.add((row[0], row[1]))

        # Делаем insert ... on conflict ... do update
        values: list[dict[str, Any]] = [
            {
                "external_id": it.external_id,
                "source_type": it.source_type,
                "title": it.title,
                "company_name": it.company_name,
                "company_id": it.company_id,
                "salary_from": it.salary_from,
                "salary_to": it.salary_to,
                "salary_currency": it.salary_currency,
                "url": it.url,
                "area_name": it.area_name,
                "schedule": it.schedule,
                "experience": it.experience,
                # description / key_skills не трогаем при коротком парсинге
                "published_at": it.published_at,
                "raw_data": it.raw_data,
            }
            for it in items
        ]
        ins_stmt = pg_insert(VacancyORM).values(values)
        # При конфликте — обновляем все обычные поля кроме description/key_skills
        # (их сами получаем через fetch_details on-demand).
        update_cols = {
            c.name: c
            for c in ins_stmt.excluded
            if c.name
            not in ("id", "external_id", "source_type", "description", "key_skills", "parsed_at")
        }
        upsert_stmt = ins_stmt.on_conflict_do_update(
            constraint="uq_vacancies_source_external",
            set_=update_cols,
        )
        await self.session.execute(upsert_stmt)
        inserted = sum(1 for it in items if (it.source_type, it.external_id) not in existing_keys)
        updated = len(items) - inserted
        return inserted, updated

    async def update_details(
        self,
        vacancy_id: int,
        *,
        description: str | None,
        key_skills: list[str] | None,
        mark_attempted: bool = False,
    ) -> None:
        """Дозаписывает description и key_skills (на on-demand fetch_details).

        mark_attempted=True ставит в raw_data флаг details_fetched, чтобы повторные
        открытия вакансии не дёргали Chrome снова (даже если описания у вакансии
        нет — например, она в архиве).
        """
        orm = await self.session.get(VacancyORM, vacancy_id)
        if orm is None:
            return
        if description is not None:
            orm.description = description
        if key_skills is not None:
            orm.key_skills = key_skills or None
        if mark_attempted:
            data = dict(orm.raw_data or {})
            data["details_fetched"] = True
            orm.raw_data = data

    async def was_details_attempted(self, vacancy_id: int) -> bool:
        """True, если детальную страницу уже пытались подгрузить (см. update_details)."""
        orm = await self.session.get(VacancyORM, vacancy_id)
        if orm is None:
            return False
        return bool((orm.raw_data or {}).get("details_fetched"))

    async def set_source_links(
        self, source_id: int, items: list[ParsedVacancy]
    ) -> None:
        """Полностью заменяет набор вакансий источника на свежий результат парсинга.

        Вызывается после upsert_many: все items уже есть в vacancies, остаётся
        связать их с источником, предварительно стерев прежние связи. Так лента
        показывает только последнюю выдачу (refresh = замена, не накопление).
        """
        await self.session.execute(
            delete(SourceVacancyORM).where(SourceVacancyORM.source_id == source_id)
        )
        if not items:
            return
        # Резолвим id вакансий по (source_type, external_id).
        by_type: dict[str, set[str]] = {}
        for it in items:
            by_type.setdefault(it.source_type, set()).add(it.external_id)
        vacancy_ids: list[int] = []
        for src_type, ext_ids in by_type.items():
            stmt = select(VacancyORM.id).where(
                VacancyORM.source_type == src_type,
                VacancyORM.external_id.in_(ext_ids),
            )
            vacancy_ids.extend(r[0] for r in (await self.session.execute(stmt)).all())
        if vacancy_ids:
            await self.session.execute(
                pg_insert(SourceVacancyORM)
                .values([{"source_id": source_id, "vacancy_id": vid} for vid in vacancy_ids])
                .on_conflict_do_nothing()
            )

    async def list_feed_for_profile(
        self,
        profile_id: int,
        *,
        limit: int = 20,
        offset: int = 0,
        reaction: str | None = None,
    ) -> list[FeedItem]:
        """Лента: вакансии из ПОСЛЕДНЕГО результата парсинга источников профиля.

        Набор задаётся таблицей source_vacancies (заменяется при каждом refresh),
        поэтому смена фильтров + «Обновить» обновляет ленту целиком, а не
        накапливает старое поверх нового. Реакции подтягиваем left-join.

        Фильтр по реакции (`reaction`):
        - None  → «Все»: скрываем пропущенные (skip), показываем остальное;
        - "all" → вообще всё, включая пропущенные (нужно странице вакансии,
                  чтобы найти свою реакцию независимо от фильтра ленты);
        - "like" / "save" / "skip" → только вакансии с этой реакцией.
        """
        # id вакансий, входящих в актуальную выдачу активных источников профиля.
        # distinct — если несколько источников вернули одну вакансию.
        vac_ids_subq = (
            select(SourceVacancyORM.vacancy_id)
            .join(SourceORM, SourceORM.id == SourceVacancyORM.source_id)
            .where(SourceORM.profile_id == profile_id, SourceORM.is_active.is_(True))
            .distinct()
            .subquery()
        )

        stmt = (
            select(VacancyORM, ReactionORM)
            .join(vac_ids_subq, vac_ids_subq.c.vacancy_id == VacancyORM.id)
            .outerjoin(
                ReactionORM,
                (ReactionORM.vacancy_id == VacancyORM.id) & (ReactionORM.profile_id == profile_id),
            )
        )
        if reaction is None:
            # «Все» — прячем пропущенные. NULL (нет реакции) остаётся в ленте.
            stmt = stmt.where(
                (ReactionORM.reaction.is_(None)) | (ReactionORM.reaction != "skip")
            )
        elif reaction != "all":
            stmt = stmt.where(ReactionORM.reaction == reaction)
        stmt = (
            stmt.order_by(VacancyORM.published_at.desc().nulls_last(), VacancyORM.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        items: list[FeedItem] = []
        for vac_orm, react_orm in result.all():
            items.append(
                FeedItem(
                    vacancy=_to_domain(vac_orm),
                    reaction=_reaction_to_domain(react_orm) if react_orm else None,
                )
            )
        return items
