from __future__ import annotations

import argparse
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from sqlalchemy import text

from src.config import load_settings
from src.db.session import create_engine, create_session_factory
from src.handlers import admin, callbacks, habits, start
from src.services.scheduler import HabitScheduler, set_scheduler_instance


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


async def run(check_only: bool = False) -> None:
    settings = load_settings()
    configure_logging(settings.log_level)

    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)

    if check_only:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        await engine.dispose()
        logging.info("Check passed: imports and database connection are OK")
        return

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(start.router)
    dp.include_router(callbacks.router)
    dp.include_router(admin.router)
    dp.include_router(habits.router)

    scheduler = HabitScheduler(bot=bot, session_factory=session_factory)
    set_scheduler_instance(scheduler)
    await scheduler.start()

    try:
        await dp.start_polling(
            bot,
            session_factory=session_factory,
            scheduler=scheduler,
            settings=settings,
        )
    finally:
        await scheduler.shutdown()
        await bot.session.close()
        await engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Telegram habit bot")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run import and DB connectivity check, then exit",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(run(check_only=args.check))


if __name__ == "__main__":
    main()
