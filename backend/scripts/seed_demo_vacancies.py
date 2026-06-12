"""Seed демо-вакансий для v0.1 beta-теста на знакомых.

Используется когда hh.ru API недоступен (ddos-guard / отключение публичного API
после 15.12.2025). Кладёт 15 реалистичных IT-вакансий прямо в Railway Postgres.

Запуск:
    # локально:
    uv run python -m scripts.seed_demo_vacancies

    # на Railway (одноразово через Run Command):
    DATABASE_URL=$DATABASE_URL python -m scripts.seed_demo_vacancies

Идемпотентно: повторный запуск НЕ создаст дубликаты (UPSERT по
source_type+external_id).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from loguru import logger

from src.db.repositories.vacancy import VacancyRepository
from src.db.session import SessionMaker
from src.domain.vacancy import ParsedVacancy
from src.logging_setup import setup_logging

_NOW = datetime.now(UTC)


def _vac(
    *,
    ext: str,
    title: str,
    company: str,
    salary_from: int | None = None,
    salary_to: int | None = None,
    area: str = "Москва",
    schedule: str = "remote",
    experience: str = "between3And6",
    description: str,
    skills: list[str],
    days_ago: int = 0,
) -> ParsedVacancy:
    return ParsedVacancy(
        external_id=ext,
        source_type="hh",
        title=title,
        company_name=company,
        company_id=f"company-{ext}",
        salary_from=salary_from,
        salary_to=salary_to,
        salary_currency="RUR" if (salary_from or salary_to) else None,
        url=f"https://hh.ru/vacancy/{ext}",
        area_name=area,
        schedule=schedule,
        experience=experience,
        description=description,
        key_skills=skills,
        published_at=_NOW - timedelta(days=days_ago, hours=days_ago * 3),
        raw_data={"seeded": True},
    )


DEMO_VACANCIES: list[ParsedVacancy] = [
    _vac(
        ext="demo-001",
        title="Senior Python Backend Engineer",
        company="Tinkoff",
        salary_from=350000,
        salary_to=500000,
        description=(
            "<p>Ищем сеньор Python разработчика в команду риск-движка. "
            "Стек: Python 3.12, FastAPI, PostgreSQL, Kafka, Kubernetes. "
            "Реальная нагрузка, sub-100ms latency.</p>"
            "<p><b>Что предлагаем:</b> офис в БЦ \"Водный\" или гибрид, ДМС "
            "со стоматологией, обучение, оплата конференций.</p>"
        ),
        skills=["python", "fastapi", "postgresql", "kafka", "kubernetes"],
        days_ago=0,
    ),
    _vac(
        ext="demo-002",
        title="Middle Python Developer",
        company="Wildberries Tech",
        salary_from=250000,
        salary_to=350000,
        description=(
            "<p>В команду расчёта комиссий нужен Python разработчик с опытом "
            "3+ года. PostgreSQL, ClickHouse, Airflow.</p>"
        ),
        skills=["python", "postgresql", "clickhouse", "airflow"],
        days_ago=1,
        schedule="fullDay",
        area="Москва",
    ),
    _vac(
        ext="demo-003",
        title="Python разработчик (Django)",
        company="DocDoc",
        salary_from=200000,
        salary_to=270000,
        description=(
            "<p>Бэкенд медицинского сервиса. Django, DRF, PostgreSQL. "
            "Гибридный график, офис у м. Белорусская.</p>"
        ),
        skills=["python", "django", "drf", "postgresql"],
        days_ago=2,
        schedule="flexible",
    ),
    _vac(
        ext="demo-004",
        title="Senior Backend Python / AI Engineer",
        company="VK AI Lab",
        salary_from=400000,
        salary_to=600000,
        description=(
            "<p>Делаем платформу для разработчиков AI-приложений. "
            "Python, FastAPI, async, LLM (OpenAI/Anthropic SDK), vector DB.</p>"
            "<p>Полная удалёнка, можно из любой точки мира с РФ налогообложением.</p>"
        ),
        skills=["python", "fastapi", "asyncio", "llm", "openai", "qdrant"],
        days_ago=0,
        experience="moreThan6",
    ),
    _vac(
        ext="demo-005",
        title="Middle Python (data engineering)",
        company="Ozon",
        salary_from=230000,
        salary_to=320000,
        description=(
            "<p>Data Platform team. Python, Spark, Kafka, Airflow. "
            "Стримы реального времени, обработка миллиардов событий в день.</p>"
        ),
        skills=["python", "spark", "kafka", "airflow", "scala"],
        days_ago=3,
        schedule="fullDay",
        area="Москва",
    ),
    _vac(
        ext="demo-006",
        title="Python разработчик в стартап",
        company="UnknownAI",
        salary_from=None,
        salary_to=None,
        description=(
            "<p>Молодая амбициозная команда! Стартап на ранней стадии. "
            "Атмосфера семьи. Готов работать как со своим домом. "
            "Бесплатный испытательный период 2 месяца.</p>"
        ),
        skills=["python"],
        days_ago=4,
    ),
    _vac(
        ext="demo-007",
        title="Junior Python Developer",
        company="ITStudio",
        salary_from=80000,
        salary_to=130000,
        description=(
            "<p>Начинающий Python разработчик в команду CRM-системы. "
            "Django, PostgreSQL. Готовы взять без коммерческого опыта если "
            "хорошая база.</p>"
        ),
        skills=["python", "django", "git"],
        days_ago=2,
        experience="between1And3",
        schedule="fullDay",
        area="Санкт-Петербург",
    ),
    _vac(
        ext="demo-008",
        title="Backend Python разработчик",
        company="Сбер",
        salary_from=280000,
        salary_to=400000,
        description=(
            "<p>В команду цифрового банка. Python, FastAPI, asyncio, "
            "PostgreSQL, gRPC. Полный цикл разработки от дизайна до прода.</p>"
        ),
        skills=["python", "fastapi", "grpc", "postgresql", "asyncio"],
        days_ago=1,
        schedule="hybrid",
        experience="between3And6",
    ),
    _vac(
        ext="demo-009",
        title="Lead Python Engineer",
        company="Yandex Cloud",
        salary_from=500000,
        salary_to=750000,
        description=(
            "<p>Lead команды Object Storage. Python, Go, distributed systems, "
            "high load. Лидерство технических решений, менторство команды из 5 человек.</p>"
        ),
        skills=["python", "go", "kubernetes", "etcd", "distributed-systems"],
        days_ago=0,
        experience="moreThan6",
    ),
    _vac(
        ext="demo-010",
        title="Python разработчик (1С интеграции)",
        company="ИнтерКомСервис",
        salary_from=150000,
        salary_to=200000,
        description=(
            "<p>Интеграция 1С с внешними API. Python, 1С, SOAP/REST.</p>"
        ),
        skills=["python", "1с", "soap"],
        days_ago=5,
        schedule="fullDay",
        area="Москва",
    ),
    _vac(
        ext="demo-011",
        title="Middle Backend Python",
        company="HeadHunter",
        salary_from=270000,
        salary_to=370000,
        description=(
            "<p>В платформенную команду hh.ru. Python, FastAPI, Tornado, "
            "PostgreSQL, Kafka. Реальный hi-load: 50М+ юзеров.</p>"
        ),
        skills=["python", "fastapi", "tornado", "kafka", "postgresql"],
        days_ago=2,
        schedule="hybrid",
    ),
    _vac(
        ext="demo-012",
        title="Python / FastAPI Engineer (remote)",
        company="Plata",
        salary_from=300000,
        salary_to=450000,
        description=(
            "<p>Fintech продукт на латиноамериканский рынок. Python 3.12, "
            "FastAPI, PostgreSQL, Redis, AWS. Команда распределена, 100% remote.</p>"
        ),
        skills=["python", "fastapi", "postgresql", "redis", "aws", "english"],
        days_ago=1,
        experience="between3And6",
    ),
    _vac(
        ext="demo-013",
        title="ML Engineer (Python)",
        company="Avito",
        salary_from=350000,
        salary_to=500000,
        description=(
            "<p>Рекомендательная система. Python, PyTorch, ClickHouse, "
            "Spark. Эксперименты с трансформерами для ранжирования.</p>"
        ),
        skills=["python", "pytorch", "clickhouse", "spark", "ml"],
        days_ago=0,
        experience="between3And6",
    ),
    _vac(
        ext="demo-014",
        title="Python разработчик в дружный коллектив",
        company="ООО Стартап",
        salary_from=None,
        salary_to=120000,
        description=(
            "<p>Ищем Python middle/senior. Стек: Python, Django, "
            "PostgreSQL, Vue.js, React, Angular, Node.js, Go, Rust, "
            "Kubernetes, AWS, Azure, GCP. 5+ лет на каждом.</p>"
            "<p>Зарплата обсуждается на собеседовании.</p>"
        ),
        skills=["python", "django", "react", "vue", "angular", "go", "rust"],
        days_ago=6,
    ),
    _vac(
        ext="demo-015",
        title="Senior Python (распределённые системы)",
        company="Selectel",
        salary_from=380000,
        salary_to=520000,
        description=(
            "<p>Платформа Managed Kubernetes. Python, Go, Kubernetes Operators, "
            "etcd. Глубокое погружение в инфру.</p>"
        ),
        skills=["python", "go", "kubernetes", "etcd", "linux"],
        days_ago=1,
        experience="moreThan6",
        schedule="remote",
    ),
]


async def main() -> int:
    setup_logging()
    logger.bind(count=len(DEMO_VACANCIES)).info("Seeding demo vacancies")

    async with SessionMaker() as session:
        repo = VacancyRepository(session)
        inserted, updated = await repo.upsert_many(DEMO_VACANCIES)
        await session.commit()

    logger.bind(inserted=inserted, updated=updated).info("Seed done")
    print(f"\nSeed complete: {inserted} new, {updated} updated.")
    print("Откройте MiniApp в Telegram и нажмите Feed — должны быть вакансии.")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(asyncio.run(main()))
