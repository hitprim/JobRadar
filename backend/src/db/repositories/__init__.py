"""Repository pattern.

Каждое repository — узкий контракт работы с одной агрегатной сущностью БД.
Возвращает domain-объекты (pydantic), а не ORM. SQL живёт ТОЛЬКО здесь.

Сервисы (`src/services/*`) принимают repositories через конструктор —
это позволяет подменять их mock'ами в тестах.
"""

from src.db.repositories.profile import ProfileRepository
from src.db.repositories.reaction import ReactionRepository
from src.db.repositories.source import SourceRepository
from src.db.repositories.user import UserRepository
from src.db.repositories.vacancy import VacancyRepository

__all__ = [
    "ProfileRepository",
    "ReactionRepository",
    "SourceRepository",
    "UserRepository",
    "VacancyRepository",
]
