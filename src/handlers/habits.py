from __future__ import annotations

from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.habits import (
    add_habit_time,
    create_habit,
    get_habit_by_id,
)
from src.services.scheduler import HabitScheduler
from src.services.ui_state import HABIT_ADD, HABIT_ADD_TIME, HABIT_VIEW, get_or_create_ui_state
from src.ui.navigation import render_screen

router = Router()


async def _delete_user_input_safe(bot: Bot, chat_id: int, message_id: int) -> None:
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramBadRequest:
        pass

@router.message(F.text, ~F.text.startswith("/"))
async def text_input_router(
    message: Message,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
) -> None:
    if not message.from_user or not message.text:
        return
    if message.text.startswith("/"):
        return
    chat_id = message.chat.id
    await _delete_user_input_safe(
        bot=bot,
        chat_id=chat_id,
        message_id=message.message_id,
    )
    async with session_factory() as session:
        ui_state = await get_or_create_ui_state(session, message.from_user.id)
        screen = ui_state.current_screen
        payload = dict(ui_state.payload or {})

    if screen == HABIT_ADD:
        await _handle_create_habit(message, bot, session_factory, scheduler, chat_id)
        return
    if screen == HABIT_ADD_TIME:
        habit_id = payload.get("habit_id")
        await _handle_add_time(
            message,
            bot,
            session_factory,
            scheduler,
            int(habit_id) if habit_id else None,
            chat_id,
        )
        return


async def _handle_create_habit(
    message: Message,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    chat_id: int,
) -> None:
    title = message.text.strip()
    if not title:
        await message.answer("Название не может быть пустым.")
        return
    if len(title) > 140:
        await message.answer("Слишком длинно. Максимум 140 символов.")
        return
    async with session_factory() as session:
        habit = await create_habit(session, message.from_user.id, title)
    await scheduler.reschedule_user_by_telegram_id(message.from_user.id)
    await render_screen(
        bot=bot,
        chat_id=chat_id,
        user_id=message.from_user.id,
        session_factory=session_factory,
        screen=HABIT_VIEW,
        payload={"habit_id": habit.id},
    )


async def _handle_add_time(
    message: Message,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    habit_id: int | None,
    chat_id: int,
) -> None:
    if not habit_id:
        await message.answer("Контекст потерян. Открой привычку заново.")
        return
    try:
        local_time = datetime.strptime(message.text.strip(), "%H:%M").time()
    except ValueError:
        await message.answer("Неверный формат. Используй HH:MM")
        return
    async with session_factory() as session:
        habit = await get_habit_by_id(session, habit_id)
        if not habit or not habit.user or habit.user.telegram_id != message.from_user.id:
            await message.answer("Нет доступа к привычке.")
            return
        try:
            await add_habit_time(session, habit_id, local_time)
        except Exception:
            await message.answer("Такое время уже добавлено.")
            return
    await scheduler.reschedule_user_by_telegram_id(message.from_user.id)
    await render_screen(
        bot=bot,
        chat_id=chat_id,
        user_id=message.from_user.id,
        session_factory=session_factory,
        screen=HABIT_VIEW,
        payload={"habit_id": habit_id},
        push=False,
    )
