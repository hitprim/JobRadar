"""CompanyReviewService: отзывы о компаниях (об отношении к соискателям).

Бизнес-правила v1:
- Компания идентифицируется по company_key (нормализованный id/имя вакансии).
- Оставить отзыв можно только если у юзера есть отклик (application) к этой
  компании — верификация через трекер (любой статус отклика подходит).
- Один отзыв на компанию от юзера: повторная отправка обновляет существующий.
- БЕЗ модерации: текст сохраняем и показываем как есть.
"""

from __future__ import annotations

from src.db.repositories.company_review import CompanyReviewRepository
from src.db.repositories.vacancy import VacancyRepository
from src.domain.company_review import (
    CompanyReviewCreate,
    CompanyReviewView,
    company_key_for,
)

# Сколько уникальных жалоб нужно, чтобы отзыв авто-скрылся (post-hoc модерация).
# Низкий порог — приложение народное и пока маленькое; пересмотреть при росте.
REPORT_HIDE_THRESHOLD = 3


class CompanyReviewServiceError(Exception):
    """Базовое исключение."""


class VacancyNotFoundError(CompanyReviewServiceError):
    """Вакансии нет в БД."""


class CompanyNotIdentifiableError(CompanyReviewServiceError):
    """У вакансии нет company_id/company_name — компанию не идентифицировать."""


class NotVerifiedError(CompanyReviewServiceError):
    """У юзера нет отклика к этой компании — отзыв оставить нельзя."""


class ReviewNotFoundError(CompanyReviewServiceError):
    """Отзыва с таким id нет."""


class CompanyReviewService:
    def __init__(
        self,
        reviews: CompanyReviewRepository,
        vacancies: VacancyRepository,
    ) -> None:
        self.reviews = reviews
        self.vacancies = vacancies

    async def view_for_vacancy(self, vacancy_id: int, user_id: int) -> CompanyReviewView:
        """Агрегат + список отзывов + мой отзыв + право оставить — для вакансии."""
        vacancy = await self.vacancies.get_by_id(vacancy_id)
        if vacancy is None:
            raise VacancyNotFoundError(f"vacancy {vacancy_id} not found")

        key = company_key_for(vacancy.company_id, vacancy.company_name)
        if key is None:
            # Компанию не идентифицировать — отзывов нет и оставить нельзя.
            return CompanyReviewView(
                company_key=None,
                company_name=vacancy.company_name,
                respect_score=None,
                review_count=0,
                can_review=False,
                my_review=None,
                reviews=[],
            )

        summary = await self.reviews.summary_for_key(key)
        reviews = await self.reviews.list_for_key(key)
        my_review = await self.reviews.get_my_review(key, user_id)
        can_review = key in await self.reviews.user_company_keys(user_id)

        return CompanyReviewView(
            company_key=key,
            company_name=vacancy.company_name,
            respect_score=summary.respect_score,
            review_count=summary.review_count,
            can_review=can_review,
            my_review=my_review,
            reviews=reviews,
        )

    async def submit_for_vacancy(
        self, vacancy_id: int, user_id: int, profile_id: int | None, data: CompanyReviewCreate
    ) -> CompanyReviewView:
        """Создаёт/обновляет отзыв после проверки верификации через трекер."""
        vacancy = await self.vacancies.get_by_id(vacancy_id)
        if vacancy is None:
            raise VacancyNotFoundError(f"vacancy {vacancy_id} not found")

        key = company_key_for(vacancy.company_id, vacancy.company_name)
        if key is None:
            raise CompanyNotIdentifiableError(f"vacancy {vacancy_id} has no company")

        if key not in await self.reviews.user_company_keys(user_id):
            raise NotVerifiedError("no application to this company")

        await self.reviews.upsert(
            company_key=key,
            company_name=vacancy.company_name,
            user_id=user_id,
            profile_id=profile_id,
            responded=data.responded,
            respect=data.respect,
            feedback=data.feedback,
            honesty=data.honesty,
            process=data.process,
            text=data.text,
        )
        # Возвращаем свежий полный взгляд (агрегат уже учитывает новый отзыв).
        return await self.view_for_vacancy(vacancy_id, user_id)

    async def report(self, review_id: int, user_id: int) -> tuple[int, bool]:
        """Жалоба на отзыв. Возвращает (число жалоб, скрыт ли теперь отзыв).

        Идемпотентно: повторная жалоба того же юзера не накручивает счётчик.
        При достижении порога отзыв авто-скрывается из публичных списков.
        """
        review = await self.reviews.get_by_id(review_id)
        if review is None:
            raise ReviewNotFoundError(f"review {review_id} not found")

        count = await self.reviews.add_report(review_id, user_id)
        hidden = count >= REPORT_HIDE_THRESHOLD
        if hidden and not review.is_hidden:
            await self.reviews.set_hidden(review_id, True)
        return count, hidden


__all__ = [
    "CompanyNotIdentifiableError",
    "CompanyReviewService",
    "CompanyReviewServiceError",
    "NotVerifiedError",
    "ReviewNotFoundError",
    "VacancyNotFoundError",
]
