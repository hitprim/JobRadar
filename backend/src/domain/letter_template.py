"""Domain-объект LetterTemplate (шаблон сопроводительного письма).

Шаблон — сохранённое пользователем письмо для переиспользования. В тексте
поддерживаются плейсхолдеры {company} и {position}, которые подставляются на
клиенте при применении шаблона к конкретной вакансии (см. фронт).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class LetterTemplate(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: int
    profile_id: int
    title: str
    body: str
    created_at: datetime
    updated_at: datetime
