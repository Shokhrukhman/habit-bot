from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.habits import get_or_create_user
from src.services.ui_state import HABITS_MENU, HOME, MONTH, SETTINGS_MENU, TIMEZONE_SELECT, TODAY
from src.ui.navigation import render_screen

router = Router()
logger = logging.getLogger(__name__)


@router.message(CommandStart())
async def start_cmd(
    message: Message,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not message.from_user:
        return
    telegram_id = message.from_user.id
    chat_id = message.chat.id
    db_user_id: int | None = None
    try:
        async with session_factory() as session:
            db_user = await get_or_create_user(session, telegram_id)
            db_user_id = db_user.id
        logger.info(
            "Command /start received: tg_id=%s chat_id=%s db_user_id=%s",
            telegram_id,
            chat_id,
            db_user_id,
        )
        await render_screen(
            bot=bot,
            chat_id=chat_id,
            user_id=db_user_id,
            session_factory=session_factory,
            screen=HOME,
            payload={},
            push=False,
        )
    except Exception:
        logger.exception(
            "Failed to render HOME via UI state: tg_id=%s chat_id=%s db_user_id=%s",
            telegram_id,
            chat_id,
            db_user_id,
        )
        kb = InlineKeyboardBuilder()
        kb.button(text="📚 Привычки", callback_data="nav:habits")
        kb.button(text="📊 Статистика", callback_data="nav:stats")
        kb.button(text="⚙️ Настройки", callback_data="nav:settings")
        kb.adjust(3)
        await message.answer(
            "HOME fallback",
            reply_markup=kb.as_markup(),
        )


@router.message(Command("home"))
async def home_cmd(
    message: Message,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not message.from_user:
        return
    chat_id = message.chat.id
    await render_screen(
        bot=bot,
        chat_id=chat_id,
        user_id=message.from_user.id,
        session_factory=session_factory,
        screen=HOME,
        payload={},
        push=False,
    )


@router.message(Command("timezone"))
async def timezone_cmd(
    message: Message,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not message.from_user:
        return
    chat_id = message.chat.id
    await render_screen(
        bot=bot,
        chat_id=chat_id,
        user_id=message.from_user.id,
        session_factory=session_factory,
        screen=TIMEZONE_SELECT,
    )


@router.message(Command("habits"))
async def habits_cmd(
    message: Message,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not message.from_user:
        return
    chat_id = message.chat.id
    await render_screen(
        bot=bot,
        chat_id=chat_id,
        user_id=message.from_user.id,
        session_factory=session_factory,
        screen=HABITS_MENU,
    )


@router.message(Command("settings"))
async def settings_cmd(
    message: Message,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not message.from_user:
        return
    chat_id = message.chat.id
    await render_screen(
        bot=bot,
        chat_id=chat_id,
        user_id=message.from_user.id,
        session_factory=session_factory,
        screen=SETTINGS_MENU,
    )


@router.message(Command("today"))
async def today_cmd(
    message: Message,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not message.from_user:
        return
    chat_id = message.chat.id
    await render_screen(
        bot=bot,
        chat_id=chat_id,
        user_id=message.from_user.id,
        session_factory=session_factory,
        screen=TODAY,
    )


@router.message(Command("month"))
async def month_cmd(
    message: Message,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not message.from_user:
        return
    chat_id = message.chat.id
    await render_screen(
        bot=bot,
        chat_id=chat_id,
        user_id=message.from_user.id,
        session_factory=session_factory,
        screen=MONTH,
    )
