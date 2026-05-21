"""Repository pattern.

Каждое repository — узкий контракт работы с одной агрегатной сущностью БД.
Возвращает domain-объекты (pydantic), а не ORM. SQL живёт ТОЛЬКО здесь.

Сервисы (`src/services/*`) принимают repositories через конструктор —
это позволяет подменять их mock'ами в тестах.
"""

from src.db.repositories.profile import ProfileRepository
from src.db.repositories.user import UserRepository

__all__ = ["ProfileRepository", "UserRepository"]
