"""LetterService: оркестрация генерации сопроводительных через LLM.

Шаги:
1. Загрузить профиль (с проверкой принадлежности юзеру).
2. Загрузить вакансию.
3. Опционально дешифровать резюме (если есть — добавляем в промпт).
4. load_prompt("letters", profile.category).
5. build_letter_user_message → user message с защитой от injection.
6. llm.complete → LetterResult.
7. Сохранить в `letters` (каждый вызов = новая запись).

Лимиты `free_letters_per_month` пока не enforce'им — в v0.1 beta_mode=true.
"""

from __future__ import annotations

from loguru import logger

from src.db.repositories.letter import LetterRepository
from src.db.repositories.profile import ProfileRepository
from src.db.repositories.user import UserRepository
from src.db.repositories.vacancy import VacancyRepository
from src.domain.letter import Letter
from src.domain.profile import Profile
from src.llm.base import LLMProvider
from src.llm.letter import LetterResult, build_letter_user_message
from src.llm.prompt_loader import load_prompt
from src.security.encryption import decrypt_resume

# Лимит длины extra_instructions (защита от попыток "переписать" промпт)
MAX_EXTRA_INSTRUCTIONS_LENGTH = 2000


class LetterServiceError(Exception):
    """Базовое исключение."""


class ProfileNotAccessibleError(LetterServiceError):
    """Профиль не найден или принадлежит другому юзеру."""


class VacancyNotFoundError(LetterServiceError):
    """Вакансии нет в БД."""


class LetterNotFoundError(LetterServiceError):
    """Письмо не найдено или принадлежит другому юзеру."""


class ExtraInstructionsTooLongError(LetterServiceError):
    """Юзер передал слишком длинный extra_instructions."""


class LetterService:
    def __init__(
        self,
        llm: LLMProvider,
        *,
        letters: LetterRepository,
        profiles: ProfileRepository,
        vacancies: VacancyRepository,
        users: UserRepository,
    ) -> None:
        self.llm = llm
        self.letters = letters
        self.profiles = profiles
        self.vacancies = vacancies
        self.users = users

    async def generate(
        self,
        *,
        vacancy_id: int,
        profile_id: int,
        user_id: int,
        extra_instructions: str | None = None,
    ) -> tuple[LetterResult, Letter]:
        if extra_instructions and len(extra_instructions) > MAX_EXTRA_INSTRUCTIONS_LENGTH:
            raise ExtraInstructionsTooLongError(
                f"extra_instructions exceeds {MAX_EXTRA_INSTRUCTIONS_LENGTH} characters"
            )

        profile = await self.profiles.get_by_id_for_user(profile_id, user_id)
        if profile is None:
            raise ProfileNotAccessibleError(f"profile {profile_id} not found")

        vacancy = await self.vacancies.get_by_id(vacancy_id)
        if vacancy is None:
            raise VacancyNotFoundError(f"vacancy {vacancy_id} not found")

        resume_text = await self._get_resume_text(profile, user_id)

        system_prompt = load_prompt("letters", profile.category)
        user_message = build_letter_user_message(
            profile, vacancy, resume_text=resume_text, extra_instructions=extra_instructions
        )

        logger.bind(
            profile_id=profile_id,
            vacancy_id=vacancy_id,
            category=profile.category,
            has_extra=bool(extra_instructions),
        ).info("letter: calling LLM")
        result = await self.llm.complete(
            system=system_prompt,
            user=user_message,
            response_schema=LetterResult,
        )

        # Сохраняем. prompt_used — путь к промпту (для аудита), без user-данных.
        letter = await self.letters.create(
            profile_id=profile_id,
            vacancy_id=vacancy_id,
            text=result.letter_text,
            prompt_used=f"letters/{profile.category}.md",
        )
        return result, letter

    async def get_for_user(self, letter_id: int, user_id: int) -> Letter:
        letter = await self.letters.get_by_id_for_user(letter_id, user_id)
        if letter is None:
            raise LetterNotFoundError(f"letter {letter_id} not found")
        return letter

    async def update_for_user(
        self,
        letter_id: int,
        user_id: int,
        *,
        text: str | None = None,
        used_in_application: bool | None = None,
    ) -> Letter:
        letter = await self.letters.update_for_user(
            letter_id, user_id, text=text, used_in_application=used_in_application
        )
        if letter is None:
            raise LetterNotFoundError(f"letter {letter_id} not found")
        return letter

    async def list_for_user_profile(
        self, profile_id: int, user_id: int, *, limit: int = 50, offset: int = 0
    ) -> list[Letter]:
        # Защита от IDOR: профиль должен принадлежать юзеру
        profile = await self.profiles.get_by_id_for_user(profile_id, user_id)
        if profile is None:
            raise ProfileNotAccessibleError(f"profile {profile_id} not found")
        return await self.letters.list_for_profile(profile_id, limit=limit, offset=offset)

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
            logger.warning("letter: failed to decrypt resume: {}", exc)
            return None
