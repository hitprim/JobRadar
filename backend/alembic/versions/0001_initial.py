"""initial schema: users, profiles, sources, vacancies, reactions, applications, letters, payments, events, config

Создаёт всю схему БД из CLAUDE.md и засевает таблицу config дефолтными значениями
(beta_mode=true, лимиты, цена пачки кредитов).

Revision ID: 0001
Revises:
Create Date: 2026-05-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # users (FK на profiles добавляется позже через ALTER из-за циклической связи)
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.Text(), nullable=True),
        sa.Column("first_name", sa.Text(), nullable=True),
        sa.Column("active_profile_id", sa.BigInteger(), nullable=True),
        sa.Column("dek_encrypted", postgresql.BYTEA(), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_active_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("telegram_id", name="uq_users_telegram_id"),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"])

    # ------------------------------------------------------------------
    # profiles
    # ------------------------------------------------------------------
    op.create_table(
        "profiles",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False, server_default="it"),
        sa.Column("stack", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("grade", sa.Text(), nullable=True),
        sa.Column("salary_from", sa.Integer(), nullable=True),
        sa.Column("salary_to", sa.Integer(), nullable=True),
        sa.Column("salary_currency", sa.Text(), nullable=True, server_default="RUR"),
        sa.Column("work_format", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("schedule", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("area_ids", postgresql.ARRAY(sa.Integer()), nullable=True),
        sa.Column("exclude_keywords", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("resume_encrypted", postgresql.BYTEA(), nullable=True),
        sa.Column("category_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_profiles_user_id", "profiles", ["user_id"])
    op.create_index("ix_profiles_user_active", "profiles", ["user_id", "is_active"])

    # Замыкаем циклическую FK users.active_profile_id -> profiles.id
    op.create_foreign_key(
        "fk_users_active_profile_id",
        source_table="users",
        referent_table="profiles",
        local_cols=["active_profile_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )

    # ------------------------------------------------------------------
    # sources
    # ------------------------------------------------------------------
    op.create_table(
        "sources",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.BigInteger(),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("search_params", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_parsed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_status", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("vacancies_today", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_sources_profile_active", "sources", ["profile_id", "is_active"])

    # ------------------------------------------------------------------
    # vacancies
    # ------------------------------------------------------------------
    op.create_table(
        "vacancies",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("company_name", sa.Text(), nullable=True),
        sa.Column("company_id", sa.Text(), nullable=True),
        sa.Column("salary_from", sa.Integer(), nullable=True),
        sa.Column("salary_to", sa.Integer(), nullable=True),
        sa.Column("salary_currency", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("area_name", sa.Text(), nullable=True),
        sa.Column("schedule", sa.Text(), nullable=True),
        sa.Column("experience", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("key_skills", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("published_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "parsed_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.UniqueConstraint("source_type", "external_id", name="uq_vacancies_source_external"),
    )
    op.create_index(
        "ix_vacancies_parsed_at_desc",
        "vacancies",
        [sa.text("parsed_at DESC")],
    )
    op.create_index("ix_vacancies_published_at", "vacancies", ["published_at"])

    # ------------------------------------------------------------------
    # vacancy_reactions
    # ------------------------------------------------------------------
    op.create_table(
        "vacancy_reactions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.BigInteger(),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "vacancy_id",
            sa.BigInteger(),
            sa.ForeignKey("vacancies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reaction", sa.Text(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("score_reason", sa.Text(), nullable=True),
        sa.Column("red_flags", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("scored_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("profile_id", "vacancy_id", name="uq_reactions_profile_vacancy"),
    )
    op.create_index(
        "ix_reactions_profile_reaction",
        "vacancy_reactions",
        ["profile_id", "reaction"],
    )
    op.create_index(
        "ix_reactions_profile_scored_at",
        "vacancy_reactions",
        ["profile_id", sa.text("scored_at DESC")],
    )

    # ------------------------------------------------------------------
    # applications
    # ------------------------------------------------------------------
    op.create_table(
        "applications",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.BigInteger(),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "vacancy_id",
            sa.BigInteger(),
            sa.ForeignKey("vacancies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="sent"),
        sa.Column("cover_letter", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("next_reminder_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("profile_id", "vacancy_id", name="uq_applications_profile_vacancy"),
    )
    op.create_index("ix_applications_profile_status", "applications", ["profile_id", "status"])
    op.create_index("ix_applications_next_reminder", "applications", ["next_reminder_at"])

    # ------------------------------------------------------------------
    # application_status_history
    # ------------------------------------------------------------------
    op.create_table(
        "application_status_history",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "application_id",
            sa.BigInteger(),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "changed_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_status_history_application",
        "application_status_history",
        ["application_id", "changed_at"],
    )

    # ------------------------------------------------------------------
    # letters
    # ------------------------------------------------------------------
    op.create_table(
        "letters",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.BigInteger(),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "vacancy_id",
            sa.BigInteger(),
            sa.ForeignKey("vacancies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("prompt_used", sa.Text(), nullable=True),
        sa.Column(
            "used_in_application",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_letters_profile_vacancy", "letters", ["profile_id", "vacancy_id"])

    # ------------------------------------------------------------------
    # payments
    # ------------------------------------------------------------------
    op.create_table(
        "payments",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount_stars", sa.Integer(), nullable=True),
        sa.Column("credits_added", sa.Integer(), nullable=True),
        sa.Column("telegram_payment_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("telegram_payment_id", name="uq_payments_telegram_payment_id"),
    )
    op.create_index(
        "ix_payments_user_created",
        "payments",
        ["user_id", sa.text("created_at DESC")],
    )

    # ------------------------------------------------------------------
    # events
    # ------------------------------------------------------------------
    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "profile_id",
            sa.BigInteger(),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_events_user_created",
        "events",
        ["user_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_events_type_created",
        "events",
        ["event_type", sa.text("created_at DESC")],
    )

    # ------------------------------------------------------------------
    # config — KV-настройки (лимиты, флаги, цены)
    # ------------------------------------------------------------------
    op.create_table(
        "config",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )

    # Seed: дефолтные значения (см. CLAUDE.md → "Конфигурация / гибкая монетизация")
    op.bulk_insert(
        sa.table(
            "config",
            sa.column("key", sa.Text()),
            sa.column("value", postgresql.JSONB(astext_type=sa.Text())),
        ),
        [
            {"key": "beta_mode", "value": True},
            {"key": "free_letters_per_month", "value": 10},
            {"key": "free_scores_per_day", "value": 50},
            {"key": "credit_pack_price_stars", "value": 50},
            {"key": "credit_pack_size", "value": 20},
            {"key": "letter_cost_credits", "value": 1},
            {"key": "score_cost_credits", "value": 0},
        ],
    )


def downgrade() -> None:
    op.drop_table("config")
    op.drop_index("ix_events_type_created", table_name="events")
    op.drop_index("ix_events_user_created", table_name="events")
    op.drop_table("events")
    op.drop_index("ix_payments_user_created", table_name="payments")
    op.drop_table("payments")
    op.drop_index("ix_letters_profile_vacancy", table_name="letters")
    op.drop_table("letters")
    op.drop_index("ix_status_history_application", table_name="application_status_history")
    op.drop_table("application_status_history")
    op.drop_index("ix_applications_next_reminder", table_name="applications")
    op.drop_index("ix_applications_profile_status", table_name="applications")
    op.drop_table("applications")
    op.drop_index("ix_reactions_profile_scored_at", table_name="vacancy_reactions")
    op.drop_index("ix_reactions_profile_reaction", table_name="vacancy_reactions")
    op.drop_table("vacancy_reactions")
    op.drop_index("ix_vacancies_published_at", table_name="vacancies")
    op.drop_index("ix_vacancies_parsed_at_desc", table_name="vacancies")
    op.drop_table("vacancies")
    op.drop_index("ix_sources_profile_active", table_name="sources")
    op.drop_table("sources")
    # Удаляем циклическую FK перед drop таблиц
    op.drop_constraint("fk_users_active_profile_id", "users", type_="foreignkey")
    op.drop_index("ix_profiles_user_active", table_name="profiles")
    op.drop_index("ix_profiles_user_id", table_name="profiles")
    op.drop_table("profiles")
    op.drop_index("ix_users_telegram_id", table_name="users")
    op.drop_table("users")
