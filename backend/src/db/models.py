"""SQLAlchemy 2.0 модели — единый файл (по соглашению из CLAUDE.md).

Все таблицы из раздела "Модель данных" CLAUDE.md.

Шифрование резюме:
- `users.dek_encrypted` — Data Encryption Key (32 байта), зашифрованный KEK из env.
- `profiles.resume_encrypted` — текст резюме, зашифрованный DEK юзера.
- Никаких plaintext-полей с резюме в БД. Никаких ПД в логах.

Все timestamp — TIMESTAMPTZ. В коде работаем в UTC, конвертация в Europe/Moscow только в UI.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, BYTEA, JSONB, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Базовый класс для всех моделей."""


# ============================================================================
# users
# ============================================================================
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(Text)
    first_name: Mapped[str | None] = mapped_column(Text)

    # Циклическая FK с profiles — резолвится через use_alter, name обязательно
    active_profile_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "profiles.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_users_active_profile_id",
        ),
        nullable=True,
    )

    # Envelope encryption: DEK юзера, зашифрованный KEK из env
    dek_encrypted: Mapped[bytes] = mapped_column(BYTEA, nullable=False)

    credits: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    # Подписка на уведомления бота (вакансии + reminders). Управляется через /notifications
    notifications_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    last_active_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    # Relationships
    profiles: Mapped[list[Profile]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="Profile.user_id",
    )
    active_profile: Mapped[Profile | None] = relationship(
        foreign_keys=[active_profile_id],
        post_update=True,  # нужно из-за циклической FK
    )


# ============================================================================
# profiles
# ============================================================================
class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    # "it" | "finance" | "sales" | "medical" | "service" | "production" | "other"
    category: Mapped[str] = mapped_column(Text, nullable=False, server_default="it")

    stack: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    # IT: "junior" | "middle" | "senior" | "lead"
    # Не-IT (v0.2+): "intern" | "specialist" | "senior" | "manager"
    grade: Mapped[str | None] = mapped_column(Text)

    salary_from: Mapped[int | None] = mapped_column(Integer)
    salary_to: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str] = mapped_column(Text, server_default="RUR")

    work_format: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    schedule: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    area_ids: Mapped[list[int] | None] = mapped_column(ARRAY(Integer))
    exclude_keywords: Mapped[list[str] | None] = mapped_column(ARRAY(Text))

    # Резюме: nonce(12) || ciphertext || tag, зашифровано DEK юзера
    resume_encrypted: Mapped[bytes | None] = mapped_column(BYTEA)

    # Категорийные специфичные поля (для v0.2+: специализация врача, тип кухни и т.п.)
    category_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="profiles", foreign_keys=[user_id])
    sources: Mapped[list[Source]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    reactions: Mapped[list[VacancyReaction]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    applications: Mapped[list[Application]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_profiles_user_active", "user_id", "is_active"),)


# ============================================================================
# sources
# ============================================================================
class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )

    # "hh" | "habr" | "custom"
    type: Mapped[str] = mapped_column(Text, nullable=False)
    search_params: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    last_parsed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_status: Mapped[str | None] = mapped_column(Text)  # "ok" | "error" | "rate_limited"
    last_error: Mapped[str | None] = mapped_column(Text)
    vacancies_today: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    profile: Mapped[Profile] = relationship(back_populates="sources")

    __table_args__ = (Index("ix_sources_profile_active", "profile_id", "is_active"),)


# ============================================================================
# vacancies
# ============================================================================
class Vacancy(Base):
    __tablename__ = "vacancies"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)

    title: Mapped[str | None] = mapped_column(Text)
    company_name: Mapped[str | None] = mapped_column(Text)
    company_id: Mapped[str | None] = mapped_column(Text)
    salary_from: Mapped[int | None] = mapped_column(Integer)
    salary_to: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    area_name: Mapped[str | None] = mapped_column(Text)
    schedule: Mapped[str | None] = mapped_column(Text)
    experience: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    key_skills: Mapped[list[str] | None] = mapped_column(ARRAY(Text))

    published_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    parsed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (
        UniqueConstraint("source_type", "external_id", name="uq_vacancies_source_external"),
        Index("ix_vacancies_parsed_at_desc", parsed_at.desc()),
        Index("ix_vacancies_published_at", "published_at"),
    )


# ============================================================================
# vacancy_reactions
# ============================================================================
class VacancyReaction(Base):
    __tablename__ = "vacancy_reactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    vacancy_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("vacancies.id", ondelete="CASCADE"), nullable=False
    )

    # "like" | "skip" | "save" | NULL (не видел)
    reaction: Mapped[str | None] = mapped_column(Text)
    score: Mapped[int | None] = mapped_column(Integer)  # 0-100
    score_reason: Mapped[str | None] = mapped_column(Text)
    red_flags: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    scored_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    profile: Mapped[Profile] = relationship(back_populates="reactions")
    vacancy: Mapped[Vacancy] = relationship()

    __table_args__ = (
        UniqueConstraint("profile_id", "vacancy_id", name="uq_reactions_profile_vacancy"),
        Index("ix_reactions_profile_reaction", "profile_id", "reaction"),
        Index("ix_reactions_profile_scored_at", "profile_id", scored_at.desc()),
    )


# ============================================================================
# applications
# ============================================================================
class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    vacancy_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("vacancies.id", ondelete="CASCADE"), nullable=False
    )

    # "sent" | "hr" | "tech" | "final" | "offer" | "reject"
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="sent")
    cover_letter: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    next_reminder_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    # Время фактической отправки напоминания. NULL = ещё не отправили.
    # После отправки next_reminder_at сбрасываем в NULL чтобы не отправить повторно.
    reminder_sent_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    profile: Mapped[Profile] = relationship(back_populates="applications")
    vacancy: Mapped[Vacancy] = relationship()
    status_history: Mapped[list[ApplicationStatusHistory]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("profile_id", "vacancy_id", name="uq_applications_profile_vacancy"),
        Index("ix_applications_profile_status", "profile_id", "status"),
        Index("ix_applications_next_reminder", "next_reminder_at"),
    )


# ============================================================================
# application_status_history
# ============================================================================
class ApplicationStatusHistory(Base):
    __tablename__ = "application_status_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    application: Mapped[Application] = relationship(back_populates="status_history")

    __table_args__ = (Index("ix_status_history_application", "application_id", "changed_at"),)


# ============================================================================
# letters
# ============================================================================
class Letter(Base):
    __tablename__ = "letters"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    vacancy_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("vacancies.id", ondelete="CASCADE"), nullable=False
    )

    text: Mapped[str | None] = mapped_column(Text)
    prompt_used: Mapped[str | None] = mapped_column(Text)
    used_in_application: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_letters_profile_vacancy", "profile_id", "vacancy_id"),)


# ============================================================================
# payments
# ============================================================================
class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    amount_stars: Mapped[int | None] = mapped_column(Integer)
    credits_added: Mapped[int | None] = mapped_column(Integer)
    telegram_payment_id: Mapped[str | None] = mapped_column(Text, unique=True)
    status: Mapped[str | None] = mapped_column(Text)  # "pending" | "success" | "failed"

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_payments_user_created", "user_id", created_at.desc()),)


# ============================================================================
# events
# ============================================================================
class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    profile_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("profiles.id", ondelete="SET NULL")
    )

    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB
    )  # колонка называется "metadata", атрибут — event_metadata (избежать SQLA-reserved name)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_events_user_created", "user_id", created_at.desc()),
        Index("ix_events_type_created", "event_type", created_at.desc()),
    )


# ============================================================================
# config — KV-настройки приложения (лимиты, флаги, цены)
# ============================================================================
class Config(Base):
    __tablename__ = "config"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
