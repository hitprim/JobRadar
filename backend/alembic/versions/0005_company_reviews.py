"""add company_reviews (отзывы о компаниях об отношении к соискателям)

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "company_reviews",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("company_key", sa.Text(), nullable=False),
        sa.Column("company_name", sa.Text(), nullable=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("profile_id", sa.BigInteger(), nullable=True),
        sa.Column("responded", sa.Text(), nullable=False),
        sa.Column("respect", sa.Text(), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=False),
        sa.Column("honesty", sa.Text(), nullable=False),
        sa.Column("process", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_key", "user_id", name="uq_company_reviews_company_user"
        ),
    )
    op.create_index(
        "ix_company_reviews_company_key", "company_reviews", ["company_key"]
    )


def downgrade() -> None:
    op.drop_index("ix_company_reviews_company_key", table_name="company_reviews")
    op.drop_table("company_reviews")
