"""ScoringService: оркестрация скоринга вакансии под профиль через LLM.

Шаги:
1. Загружаем профиль (с проверкой принадлежности юзеру).
2. Загружаем вакансию.
3. Опционально дешифруем резюме (если есть и нужно — добавим в промпт).
4. load_prompt("scoring", profile.category) → system promt.
5. build_scoring_user_message → user message с защитой от injection.
6. llm.complete → ScoringResult.
7. UPSERT в vacancy_reactions (score, score_reason, red_flags, scored_at).

Кэширование: если в reactions уже есть score — НЕ перескорим автоматически.
Решение делает caller (endpoint): `force=True` → перескор.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.db.models import VacancyReaction as ReactionORM
from src.db.repositories.profile import ProfileRepository
from src.db.repositories.reaction import ReactionRepository
from src.db.repositories.user import UserRepository
from src.db.repositories.vacancy import VacancyRepository
from src.domain.profile import Profile
from src.domain.vacancy import VacancyReaction
from src.llm.base import LLMProvider
from src.llm.prompt_loader import load_prompt
from src.llm.scoring import ScoringResult, build_scoring_user_message
from src.security.encryption import decrypt_resume


class ScoringServiceError(Exception):
    """Базовое исключение скоринг-сервиса."""


class ProfileNotAccessibleError(ScoringServiceError):
    """Профиль не найден или принадлежит другому юзеру."""


class VacancyNotFoundError(ScoringServiceError):
    """Вакансии нет в БД."""


class ScoringService:
    def __init__(
        self,
        llm: LLMProvider,
        *,
        profiles: ProfileRepository,
        vacancies: VacancyRepository,
        reactions: ReactionRepository,
        users: UserRepository,
    ) -> None:
        self.llm = llm
        self.profiles = profiles
        self.vacancies = vacancies
        self.reactions = reactions
        self.users = users

    async def score_vacancy(
        self,
        *,
        vacancy_id: int,
        profile_id: int,
        user_id: int,
        force: bool = False,
    ) -> tuple[ScoringResult, VacancyReaction, bool]:
        """Возвращает (result, reaction, used_cache).

        used_cache=True означает что LLM не вызывался — взяли из reactions.
        """
        profile = await self.profiles.get_by_id_for_user(profile_id, user_id)
        if profile is None:
            raise ProfileNotAccessibleError(f"profile {profile_id} not found")

        vacancy = await self.vacancies.get_by_id(vacancy_id)
        if vacancy is None:
            raise VacancyNotFoundError(f"vacancy {vacancy_id} not found")

        # Cache hit?
        if not force:
            existing = await self.reactions.get(profile_id=profile_id, vacancy_id=vacancy_id)
            if existing is not None and existing.score is not None:
                # Восстанавливаем ScoringResult из persisted полей
                cached = ScoringResult(
                    score=existing.score,
                    reason=existing.score_reason or "",
                    red_flags=existing.red_flags,
                    green_flags=[],  # green_flags не персистим в reactions
                )
                logger.bind(profile_id=profile_id, vacancy_id=vacancy_id).info(
                    "scoring: cache hit, skipping LLM"
                )
                return cached, existing, True

        # Подгружаем резюме если есть (для лучшего промпта)
        resume_text = await self._get_resume_text(profile, user_id)

        # Загружаем промпт по категории профиля
        system_prompt = load_prompt("scoring", profile.category)
        user_message = build_scoring_user_message(profile, vacancy, resume_text)

        logger.bind(
            profile_id=profile_id,
            vacancy_id=vacancy_id,
            category=profile.category,
        ).info("scoring: calling LLM")
        result = await self.llm.complete(
            system=system_prompt,
            user=user_message,
            response_schema=ScoringResult,
        )

        # Persist в reactions
        reaction = await self._persist_scoring(
            profile_id=profile_id, vacancy_id=vacancy_id, result=result
        )
        return result, reaction, False

    async def _get_resume_text(self, profile: Profile, user_id: int) -> str | None:
        if not profile.has_resume:
            return None
        wrapped_dek = await self.users.get_dek_wrapped(user_id)
        if wrapped_dek is None:
            return None
        blob = await self.profiles.get_resume_encrypted(profile.id, user_id)
        if blob is None:
            return None
        try:
            return decrypt_resume(wrapped_dek, blob)
        except Exception as exc:
            logger.warning("scoring: failed to decrypt resume: {}", exc)
            return None

    async def _persist_scoring(
        self,
        *,
        profile_id: int,
        vacancy_id: int,
        result: ScoringResult,
    ) -> VacancyReaction:
        now = datetime.now(UTC)
        values: dict[str, Any] = {
            "profile_id": profile_id,
            "vacancy_id": vacancy_id,
            "score": int(result.score),
            "score_reason": result.reason,
            "red_flags": result.red_flags or None,
            "scored_at": now,
        }
        stmt = (
            pg_insert(ReactionORM)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_reactions_profile_vacancy",
                set_={
                    "score": values["score"],
                    "score_reason": values["score_reason"],
                    "red_flags": values["red_flags"],
                    "scored_at": values["scored_at"],
                },
            )
            .returning(ReactionORM)
        )
        orm = (await self.reactions.session.execute(stmt)).scalar_one()
        return VacancyReaction(
            id=orm.id,
            profile_id=orm.profile_id,
            vacancy_id=orm.vacancy_id,
            reaction=orm.reaction,
            score=orm.score,
            score_reason=orm.score_reason,
            red_flags=list(orm.red_flags or []),
            scored_at=orm.scored_at,
        )

    # Вспомогательно для тестов / endpoint'ов
    async def get_cached(self, *, profile_id: int, vacancy_id: int) -> VacancyReaction | None:
        return await self.reactions.get(profile_id=profile_id, vacancy_id=vacancy_id)
