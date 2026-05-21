"""FastAPI dependencies для аутентификации.

Использование в endpoints:

    from src.security.deps import CurrentUserId

    @router.get("/me")
    async def me(user_id: CurrentUserId) -> dict[str, int]:
        return {"user_id": user_id}

Если Authorization header отсутствует или невалиден — 401 Unauthorized.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.security.jwt import InvalidTokenError, TokenClaims, decode_access_token

# auto_error=True → FastAPI сам вернёт 403 при отсутствии header.
# Делаем auto_error=False чтобы вернуть 401 с собственным сообщением.
_bearer = HTTPBearer(auto_error=False, description="JWT access token")


def get_current_claims(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> TokenClaims:
    """Извлекает и валидирует JWT из Authorization: Bearer ... header."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return decode_access_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_user_id(
    claims: Annotated[TokenClaims, Depends(get_current_claims)],
) -> int:
    """Удобная dependency: возвращает только user_id."""
    return claims.user_id


# Typed aliases для лаконичности в endpoints
CurrentClaims = Annotated[TokenClaims, Depends(get_current_claims)]
CurrentUserId = Annotated[int, Depends(get_current_user_id)]
