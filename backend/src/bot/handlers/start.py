"""Handlers для команды /start и /notifications."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)
from loguru import logger
from sqlalchemy import update

from src.config import settings
from src.db.models import User as UserORM
from src.db.session import SessionMaker

router = Router(name="start")


def _miniapp_keyboard() -> InlineKeyboardMarkup:
    if not settings.miniapp_url:
        return InlineKeyboardMarkup(inline_keyboard=[])
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть JobRadar",
                    web_app=WebAppInfo(url=settings.miniapp_url),
                )
            ]
        ]
    )


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    tg_id = message.from_user.id if message.from_user else 0
    # Ensure notifications включены (если юзер раньше делал /notifications off
    # и вернулся через /start — снова подписываем)
    async with SessionMaker() as session:
        await session.execute(
            update(UserORM).where(UserORM.telegram_id == tg_id).values(notifications_enabled=True)
        )
        await session.commit()

    await message.answer(
        "Привет! Я JobRadar — помогаю искать работу через AI.\n\n"
        "Открой мини-приложение, чтобы создать профиль и начать поиск.\n\n"
        "Команды:\n"
        "  /notifications off — отписаться от уведомлений\n"
        "  /notifications on — снова подписаться",
        reply_markup=_miniapp_keyboard(),
    )


@router.message(Command("notifications"))
async def cmd_notifications(message: Message, command: CommandObject) -> None:
    arg = (command.args or "").strip().lower()
    if arg not in ("on", "off"):
        await message.answer(
            "Использование: `/notifications on` или `/notifications off`",
            parse_mode="Markdown",
        )
        return

    enabled = arg == "on"
    tg_id = message.from_user.id if message.from_user else 0
    async with SessionMaker() as session:
        from sqlalchemy import select as _select

        exists = (
            await session.execute(_select(UserORM.id).where(UserORM.telegram_id == tg_id))
        ).scalar_one_or_none()
        if exists is None:
            await message.answer("Сначала откройте мини-приложение и создайте профиль.")
            return
        await session.execute(
            update(UserORM)
            .where(UserORM.telegram_id == tg_id)
            .values(notifications_enabled=enabled)
        )
        await session.commit()

    logger.bind(telegram_id=tg_id, enabled=enabled).info("notifications toggled")
    await message.answer("✓ Уведомления включены." if enabled else "✓ Уведомления отключены.")


# Любое неузнанное сообщение → подсказка
@router.message(F.text)
async def fallback(message: Message) -> None:
    await message.answer(
        "Не понял команду. Используйте /start чтобы открыть JobRadar.",
        reply_markup=_miniapp_keyboard(),
    )
