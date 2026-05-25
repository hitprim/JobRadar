"""Aiogram бот: long polling, отдельный процесс.

Запуск:
    uv run python -m src.bot.main

В prod (Railway): отдельный worker dyno командой `python -m src.bot.main`.
"""

from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from loguru import logger

from src.bot.handlers import start as start_handlers
from src.config import settings
from src.logging_setup import setup_logging


async def main() -> None:
    setup_logging()
    logger.info("JobRadar bot starting (long-polling)")

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(start_handlers.router)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        logger.info("JobRadar bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
