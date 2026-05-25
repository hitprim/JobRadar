"""add users.notifications_enabled and applications.reminder_sent_at

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # users.notifications_enabled
    op.add_column(
        "users",
        sa.Column(
            "notifications_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )

    # applications.reminder_sent_at
    op.add_column(
        "applications",
        sa.Column(
            "reminder_sent_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )
    # Индекс для джоба send_reminders: where next_reminder_at <= now()
    op.create_index(
        "ix_applications_next_reminder_pending",
        "applications",
        ["next_reminder_at"],
        postgresql_where=sa.text("next_reminder_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_applications_next_reminder_pending",
        table_name="applications",
        postgresql_where=sa.text("next_reminder_at IS NOT NULL"),
    )
    op.drop_column("applications", "reminder_sent_at")
    op.drop_column("users", "notifications_enabled")
