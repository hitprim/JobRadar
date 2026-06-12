"""add profiles.experience (hh experience levels for search filter)

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Явный пользовательский фильтр по опыту работы (значения hh:
    # noExperience | between1And3 | between3And6 | moreThan6). Пусто/NULL = не
    # фильтруем. Отдельно от grade: grade нужен LLM-скорингу, experience — поиску.
    op.add_column(
        "profiles",
        sa.Column("experience", postgresql.ARRAY(sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("profiles", "experience")
