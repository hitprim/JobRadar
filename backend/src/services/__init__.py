"""Бизнес-логика. Оркестрирует repositories, LLM, sources.

Модули:
- scoring.py    — скоринг вакансий через LLM (выбор промпта по profile.category)
- letter_gen.py — генерация сопроводительных
- tracker.py    — управление откликами и историей статусов
- billing.py    — учёт кредитов и расход на операции (в v0.1 заглушка с beta_mode)
- scheduler.py  — in-process scheduler v0.1 (APScheduler). В v0.2 — миграция на n8n.
"""
