"""add source_vacancies link table (current parse result per source)

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # M:N source↔vacancy: какие вакансии входят в ПОСЛЕДНИЙ результат парсинга
    # источника. При refresh набор связей источника заменяется целиком, поэтому
    # лента показывает свежую выдачу, а не старое + новое.
    op.create_table(
        "source_vacancies",
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("vacancy_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vacancy_id"], ["vacancies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("source_id", "vacancy_id"),
    )
    op.create_index(
        "ix_source_vacancies_vacancy", "source_vacancies", ["vacancy_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_source_vacancies_vacancy", table_name="source_vacancies")
    op.drop_table("source_vacancies")
