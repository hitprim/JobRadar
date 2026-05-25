"""Billing: минимальный stub в v0.1.

В v0.1 — `beta_mode=true` (см. seed таблицы config), всё бесплатно.
Endpoint возвращает {credits, beta_mode} чтобы фронт мог показать "Бета".

Invoice/webhook — на Day 27+ (Telegram Stars реальные).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Config as ConfigORM
from src.db.models import User as UserORM
from src.db.session import get_session
from src.security.deps import CurrentUserId

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class BillingPublic(BaseModel):
    credits: int
    beta_mode: bool
    free_letters_per_month: int
    free_scores_per_day: int


async def _load_config(session: AsyncSession) -> dict[str, Any]:
    rows = (await session.execute(select(ConfigORM.key, ConfigORM.value))).all()
    return {key: value for key, value in rows}


@router.get(
    "/api/billing/credits",
    response_model=BillingPublic,
    tags=["billing"],
)
async def get_credits(session: SessionDep, user_id: CurrentUserId) -> BillingPublic:
    user = await session.get(UserORM, user_id)
    cfg = await _load_config(session)
    return BillingPublic(
        credits=user.credits if user else 0,
        beta_mode=bool(cfg.get("beta_mode", True)),
        free_letters_per_month=int(cfg.get("free_letters_per_month", 10)),
        free_scores_per_day=int(cfg.get("free_scores_per_day", 50)),
    )
