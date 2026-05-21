"""Эталонный датасет для проверки качества скоринга.

Каждый кейс — пара (профиль, вакансия) + ожидания:
- score_range: диапазон, в котором должен лежать score LLM
- must_have_red_flags: ключевые слова которые должны быть в red_flags
- must_have_green_flags: ключевые слова в green_flags
- description: для документации

В CI прогоняется через `test_golden_dataset.py` — БЕЗ вызова LLM, проверяет только
валидность данных и структуру.

С реальным LLM прогоняется через `scripts/eval_scoring.py` — не в CI.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from src.domain.profile import Profile
from src.domain.vacancy import Vacancy


class EvalCase(BaseModel):
    name: str
    description: str
    profile: Profile
    vacancy: Vacancy
    score_range: tuple[int, int]
    must_have_red_flag_keywords: list[str] = []
    must_have_green_flag_keywords: list[str] = []


def _now() -> datetime:
    return datetime.now(UTC)


def _make_profile(**overrides: Any) -> Profile:
    base: dict[str, Any] = {
        "id": 1,
        "user_id": 1,
        "name": "Backend",
        "category": "it",
        "stack": [],
        "grade": None,
        "salary_from": None,
        "salary_to": None,
        "salary_currency": "RUR",
        "work_format": [],
        "schedule": [],
        "area_ids": [],
        "exclude_keywords": [],
        "has_resume": False,
        "category_data": None,
        "is_active": True,
        "created_at": _now(),
        "updated_at": _now(),
    }
    base.update(overrides)
    return Profile.model_validate(base)


def _make_vacancy(**overrides: Any) -> Vacancy:
    base: dict[str, Any] = {
        "id": 1,
        "external_id": "v1",
        "source_type": "hh",
        "title": "",
        "company_name": None,
        "company_id": None,
        "salary_from": None,
        "salary_to": None,
        "salary_currency": None,
        "url": None,
        "area_name": None,
        "schedule": None,
        "experience": None,
        "description": None,
        "key_skills": [],
        "published_at": _now(),
        "parsed_at": _now(),
    }
    base.update(overrides)
    return Vacancy.model_validate(base)


GOLDEN_CASES: list[EvalCase] = [
    EvalCase(
        name="perfect_match_senior_python_remote",
        description="Senior Python remote → senior python remote вакансия с хорошей ЗП",
        profile=_make_profile(
            stack=["python", "fastapi", "postgresql", "redis", "docker"],
            grade="senior",
            salary_from=300000,
            salary_to=400000,
            work_format=["remote"],
            schedule=["fullDay"],
        ),
        vacancy=_make_vacancy(
            title="Senior Python Backend Engineer",
            company_name="TechCorp",
            salary_from=350000,
            salary_to=450000,
            salary_currency="RUR",
            schedule="remote",
            experience="moreThan6",
            description=(
                "Ищем senior python разработчика. FastAPI, PostgreSQL, Redis, "
                "Docker. Удалёнка, full-time. Современный стек, mature team."
            ),
            key_skills=["python", "fastapi", "postgresql", "redis", "docker"],
        ),
        score_range=(75, 100),
        must_have_green_flag_keywords=[],  # не настаиваем на конкретных словах
    ),
    EvalCase(
        name="weak_match_wrong_stack",
        description="Python разработчик ↔ PHP вакансия",
        profile=_make_profile(
            stack=["python", "django"],
            grade="middle",
            salary_from=180000,
            work_format=["remote"],
        ),
        vacancy=_make_vacancy(
            title="Middle PHP Laravel Developer",
            company_name="WebStudio",
            salary_from=150000,
            salary_to=220000,
            salary_currency="RUR",
            schedule="fullDay",
            experience="between3And6",
            description="PHP/Laravel, MySQL. Офис в центре.",
            key_skills=["php", "laravel", "mysql"],
        ),
        score_range=(0, 30),
    ),
    EvalCase(
        name="suspicious_no_salary_unpaid_trial",
        description="Подозрительная вакансия: нет зарплаты, неоплачиваемый стажёрский месяц",
        profile=_make_profile(
            stack=["python", "fastapi"],
            grade="middle",
            salary_from=200000,
        ),
        vacancy=_make_vacancy(
            title="Python разработчик в дружную команду",
            company_name="NewStartup",
            description=(
                "Молодая амбициозная команда! Стартап на ранней стадии. "
                "Бесплатный испытательный срок 2 месяца, далее обсуждается. "
                "Атмосфера семьи. Готов работать как со своим домом."
            ),
            key_skills=["python"],
        ),
        score_range=(0, 35),
        must_have_red_flag_keywords=[],  # любой red_flag достаточно
    ),
    EvalCase(
        name="grade_mismatch_junior_to_senior",
        description="Junior профиль ↔ senior+ требования",
        profile=_make_profile(
            stack=["python"],
            grade="junior",
            salary_from=80000,
        ),
        vacancy=_make_vacancy(
            title="Lead Python Architect",
            company_name="BigCorp",
            salary_from=500000,
            salary_to=700000,
            salary_currency="RUR",
            experience="moreThan6",
            description=(
                "Архитектор Python с 10+ годами опыта. Лидерские навыки, "
                "выстраивание команд. Знание Kubernetes, AWS, design patterns."
            ),
            key_skills=["python", "kubernetes", "aws", "architecture"],
        ),
        score_range=(0, 35),
    ),
    EvalCase(
        name="solid_match_middle_django",
        description="Middle Django разработчик ↔ middle Django вакансия с указанной ЗП",
        profile=_make_profile(
            stack=["python", "django", "postgresql"],
            grade="middle",
            salary_from=200000,
            salary_to=280000,
            work_format=["remote", "hybrid"],
        ),
        vacancy=_make_vacancy(
            title="Middle Django Developer",
            company_name="Acme",
            salary_from=220000,
            salary_to=280000,
            salary_currency="RUR",
            schedule="remote",
            experience="between3And6",
            description="Django, DRF, PostgreSQL. Удалёнка/гибрид.",
            key_skills=["python", "django", "postgresql"],
        ),
        score_range=(60, 95),
    ),
    EvalCase(
        name="excluded_keyword",
        description="exclude_keywords содержит '1с' → вакансия 1С должна получить низкий score",
        profile=_make_profile(
            stack=["python"],
            grade="middle",
            exclude_keywords=["1с", "битрикс"],
        ),
        vacancy=_make_vacancy(
            title="Программист 1С",
            company_name="Завод",
            description="1С Бухгалтерия, 1С УТ. Конфигурация и доработка.",
            key_skills=["1с", "битрикс"],
        ),
        score_range=(0, 25),
        must_have_red_flag_keywords=[],
    ),
    EvalCase(
        name="empty_vacancy",
        description="Пустая вакансия (минимум полей) → низкий score, объяснение",
        profile=_make_profile(stack=["python"], grade="middle"),
        vacancy=_make_vacancy(title="Разработчик", description=""),
        score_range=(0, 25),
    ),
]
