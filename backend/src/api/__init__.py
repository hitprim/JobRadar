"""HTTP-роутеры FastAPI.

Здесь только HTTP-роутинг, валидация (pydantic-схемы из api/schemas.py)
и вызов сервисов из `src/services/`. Никакой бизнес-логики или SQL.

Модули будут добавляться по мере реализации:
- auth.py     — Telegram initData → JWT (День 3-4)
- profiles.py — CRUD профилей (День 3-4)
- sources.py  — настройки источников (День 5-7)
- vacancies.py — лента вакансий, реакции (День 5-7 + День 8-9)
- letters.py  — генерация сопроводительных (День 10-11)
- tracker.py  — трекер откликов (День 12-14)
- billing.py  — Telegram Stars и кредиты (v0.2, в v0.1 — заглушка)
"""
