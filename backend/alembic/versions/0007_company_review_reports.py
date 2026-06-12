"""add company_review_reports + is_hidden (жалобы на отзывы, авто-скрытие)

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "company_reviews",
        sa.Column(
            "is_hidden",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.create_table(
        "company_review_reports",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("review_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["review_id"], ["company_reviews.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "review_id", "user_id", name="uq_company_review_reports_review_user"
        ),
    )
    op.create_index(
        "ix_company_review_reports_review",
        "company_review_reports",
        ["review_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_company_review_reports_review", table_name="company_review_reports"
    )
    op.drop_table("company_review_reports")
    op.drop_column("company_reviews", "is_hidden")
