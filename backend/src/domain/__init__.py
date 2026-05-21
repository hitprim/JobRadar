"""Domain-объекты (чистые pydantic типы).

Без HTTP, без SQL, без LLM. Используются как внутренний контракт между
слоями api/, services/, db/, sources/, llm/.

Маппинг ORM → domain и domain → DTO делается руками в сервисах
(см. правило в CLAUDE.md → "Чистая архитектура").
"""
