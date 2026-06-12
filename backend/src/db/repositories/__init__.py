"""Repository pattern.

Каждое repository — узкий контракт работы с одной агрегатной сущностью БД.
Возвращает domain-объекты (pydantic), а не ORM. SQL живёт ТОЛЬКО здесь.

Сервисы (`src/services/*`) принимают repositories через конструктор —
это позволяет подменять их mock'ами в тестах.
"""

from src.db.repositories.application import ApplicationRepository
from src.db.repositories.company_review import CompanyReviewRepository
from src.db.repositories.letter import LetterRepository
from src.db.repositories.letter_template import LetterTemplateRepository
from src.db.repositories.profile import ProfileRepository
from src.db.repositories.reaction import ReactionRepository
from src.db.repositories.source import SourceRepository
from src.db.repositories.user import UserRepository
from src.db.repositories.vacancy import VacancyRepository

__all__ = [
    "ApplicationRepository",
    "CompanyReviewRepository",
    "LetterRepository",
    "LetterTemplateRepository",
    "ProfileRepository",
    "ReactionRepository",
    "SourceRepository",
    "UserRepository",
    "VacancyRepository",
]
