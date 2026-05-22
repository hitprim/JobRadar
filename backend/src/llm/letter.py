"""LLM-генерация сопроводительных писем.

`LetterResult` — pydantic-схема ответа LLM. `letter_text` — то что увидит юзер,
`draft_notes` — массив строк с заметками о том, что использовано из вакансии и
профиля (для аудита; в UI не показываем по умолчанию).

`build_letter_user_message` — упаковывает profile + vacancy + extra_instructions
в безопасный формат с той же защитой от prompt injection что в scoring (теги
<user_input>/<profile>/<vacancy>/<extra_instructions>, эскейп закрывающих
тегов, truncate до LLM_FIELD_MAX_CHARS).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.config import settings
from src.domain.profile import Profile
from src.domain.vacancy import Vacancy
from src.llm.scoring import _format_block, _format_salary, _sanitize


class LetterResult(BaseModel):
    """JSON-ответ LLM для сопроводительного письма."""

    letter_text: str = Field(
        min_length=200,
        max_length=2500,
        description="The cover letter body in Russian, ready to send. Plain text, "
        "no markdown, no signature. 150-400 words typical.",
    )
    draft_notes: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Short audit notes: which facts from vacancy/profile were used. "
        "Example: 'mentioned company's K8s focus', 'highlighted profile's 5y Python'.",
    )


# Дополнительный тег для extra_instructions — добавляем в список эскейпа.
_EXTRA_TAG = "extra_instructions"


def _sanitize_with_extra(text: str | None) -> str:
    """Расширенный sanitize для letter context — эскейп ещё одного тега."""
    if not text:
        return ""
    base = _sanitize(text)
    return base.replace(f"</{_EXTRA_TAG}>", f"</ {_EXTRA_TAG}>")


def build_letter_user_message(
    profile: Profile,
    vacancy: Vacancy,
    resume_text: str | None = None,
    extra_instructions: str | None = None,
) -> str:
    """Формирует user-message для LLM. Profile + vacancy + опц. инструкции."""
    profile_block: dict[str, Any] = {
        "name": _sanitize(profile.name),
        "category": profile.category,
        "grade": profile.grade,
        "stack": profile.stack,
        "desired_salary": _format_salary(
            profile.salary_from, profile.salary_to, profile.salary_currency
        ),
    }
    if resume_text:
        profile_block["resume"] = _sanitize(resume_text)

    vacancy_block: dict[str, Any] = {
        "title": _sanitize(vacancy.title),
        "company": _sanitize(vacancy.company_name),
        "salary": _format_salary(vacancy.salary_from, vacancy.salary_to, vacancy.salary_currency),
        "area": _sanitize(vacancy.area_name),
        "key_skills": vacancy.key_skills,
        "description": _sanitize(vacancy.description),
    }

    parts = [
        "<user_input>",
        "<profile>",
        _format_block(profile_block),
        "</profile>",
        "",
        "<vacancy>",
        _format_block(vacancy_block),
        "</vacancy>",
    ]
    if extra_instructions:
        truncated = _sanitize_with_extra(extra_instructions)
        # Ограничим длину extra_instructions отдельно — это user input, не должен
        # доминировать в промпте
        truncated = truncated[: min(len(truncated), settings.llm_field_max_chars // 4)]
        parts.extend(["", f"<{_EXTRA_TAG}>", truncated, f"</{_EXTRA_TAG}>"])
    parts.append("</user_input>")
    return "\n".join(parts) + "\n"
