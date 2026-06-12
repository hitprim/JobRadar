"""Domain-объекты для отзывов о компаниях (об отношении к соискателям).

Это НЕ «отзыв сотрудника» как на hh.ru, а оценка качества взаимодействия
кандидата с HR/компанией в процессе найма. Цель — чтобы соискатели понимали,
как компания относится к людям на этапе откликов и собеседований.

Дизайн v1 (согласован с владельцем продукта):
- Отзыв привязан к компании через нормализованный `company_key`.
- Оставить отзыв может только тот, у кого есть отклик (application) к этой
  компании — верификация через трекер.
- Структурные сигналы (5 штук) + опциональный свободный текст.
- БЕЗ жёсткой модерации: приложение народное, честность важнее причёсанности —
  текст показываем как есть. (Жалобы/модерация — отдельный трек, см. TECHDEBT.)
- Взвешенный respect-score 0-100: «ответили» и «уважение» весят больше.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ----------------------------------------------------------------------------
# Сигналы (структурные оценки). Значения — англ. коды, RU-лейблы живут на фронте.
# Порядок в каждом tuple: лучший → худший.
# ----------------------------------------------------------------------------
Responded = Literal["fast", "slow", "ignored"]  # как быстро ответили на отклик
Respect = Literal["respectful", "neutral", "dismissive"]  # тон общения
Feedback = Literal["detailed", "formal", "none"]  # обратная связь после отказа
Honesty = Literal["matched", "minor", "mismatch"]  # вакансия vs реальность
Process = Literal["smooth", "tolerable", "draining"]  # адекватность этапов/сроков

RESPONDED_VALUES: tuple[Responded, ...] = ("fast", "slow", "ignored")
RESPECT_VALUES: tuple[Respect, ...] = ("respectful", "neutral", "dismissive")
FEEDBACK_VALUES: tuple[Feedback, ...] = ("detailed", "formal", "none")
HONESTY_VALUES: tuple[Honesty, ...] = ("matched", "minor", "mismatch")
PROCESS_VALUES: tuple[Process, ...] = ("smooth", "tolerable", "draining")

# Каждый сигнал → нормированная польза 0.0 (худшее) .. 1.0 (лучшее).
_SIGNAL_SCORE: dict[str, float] = {
    # responded
    "fast": 1.0,
    "slow": 0.5,
    "ignored": 0.0,
    # respect
    "respectful": 1.0,
    "neutral": 0.5,
    "dismissive": 0.0,
    # feedback
    "detailed": 1.0,
    "formal": 0.5,
    "none": 0.0,
    # honesty
    "matched": 1.0,
    "minor": 0.5,
    "mismatch": 0.0,
    # process
    "smooth": 1.0,
    "tolerable": 0.5,
    "draining": 0.0,
}

# Веса сигналов (в сумме 1.0). «Ответили» и «уважение» весят больше —
# это самое болезненное для соискателя: игнор и пренебрежение.
_WEIGHTS: dict[str, float] = {
    "responded": 0.30,
    "respect": 0.30,
    "feedback": 0.13,
    "honesty": 0.14,
    "process": 0.13,
}


def compute_review_score(
    responded: Responded,
    respect: Respect,
    feedback: Feedback,
    honesty: Honesty,
    process: Process,
) -> int:
    """Взвешенный respect-score одного отзыва: 0..100 (целое)."""
    weighted = (
        _WEIGHTS["responded"] * _SIGNAL_SCORE[responded]
        + _WEIGHTS["respect"] * _SIGNAL_SCORE[respect]
        + _WEIGHTS["feedback"] * _SIGNAL_SCORE[feedback]
        + _WEIGHTS["honesty"] * _SIGNAL_SCORE[honesty]
        + _WEIGHTS["process"] * _SIGNAL_SCORE[process]
    )
    return round(weighted * 100)


def company_key_for(company_id: str | None, company_name: str | None) -> str | None:
    """Нормализованный ключ компании для группировки отзывов.

    Приоритет — стабильный ID работодателя (hh employer id): он не зависит от
    написания названия. Если ID нет — нормализуем имя (lower + схлопывание
    пробелов). Если нет ни того, ни другого — None (отзыв оставить нельзя).

    Логика намеренно простая и детерминированная, чтобы один и тот же
    работодатель из разных вакансий сводился к одному ключу.
    """
    if company_id:
        cid = company_id.strip()
        if cid:
            return f"id:{cid}"
    if company_name:
        norm = " ".join(company_name.lower().split())
        if norm:
            return f"name:{norm}"
    return None


# ----------------------------------------------------------------------------
# Domain-модели
# ----------------------------------------------------------------------------
class CompanyReview(BaseModel):
    """Отзыв из БД."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: int
    company_key: str
    company_name: str | None
    user_id: int
    profile_id: int | None
    responded: Responded
    respect: Respect
    feedback: Feedback
    honesty: Honesty
    process: Process
    text: str | None
    score: int
    is_hidden: bool = False
    created_at: datetime
    updated_at: datetime


class CompanyReviewCreate(BaseModel):
    """Внутренний контракт создания/обновления отзыва (сигналы + текст)."""

    responded: Responded
    respect: Respect
    feedback: Feedback
    honesty: Honesty
    process: Process
    text: str | None = Field(default=None, max_length=2000)


class CompanyReviewSummary(BaseModel):
    """Агрегат по компании: средний respect-score и число отзывов."""

    model_config = ConfigDict(frozen=True)

    company_key: str
    respect_score: int | None  # None если отзывов нет
    review_count: int


class CompanyReviewView(BaseModel):
    """Полный взгляд на отзывы компании для экрана вакансии.

    Собирается сервисом: агрегат + список отзывов + мой отзыв + право оставить.
    company_key=None означает «у вакансии нет идентифицируемой компании» —
    отзыв оставить нельзя.
    """

    model_config = ConfigDict(frozen=True)

    company_key: str | None
    company_name: str | None
    respect_score: int | None
    review_count: int
    can_review: bool  # есть ли у юзера отклик к этой компании (верификация)
    my_review: CompanyReview | None
    reviews: list[CompanyReview]
