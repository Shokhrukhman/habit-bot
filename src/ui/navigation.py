from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.ui_state import HOME, SCREEN_NAMES, get_or_create_ui_state, save_ui_state
from src.ui import strings as ui_str
from src.ui.renderer import render_by_screen

logger = logging.getLogger(__name__)


async def ensure_screen_message(
    bot: Bot,
    chat_id: int,
    user_id: int,
    session_factory: async_sessionmaker[AsyncSession],
) -> int:
    async with session_factory() as session:
        ui_state = await get_or_create_ui_state(session, user_id)
        if ui_state.screen_message_id:
            logger.info(
                "ensure_screen_message: reuse message_id=%s for identity=%s",
                ui_state.screen_message_id,
                user_id,
            )
            return int(ui_state.screen_message_id)
        message = await bot.send_message(chat_id=chat_id, text=ui_str.OPENING_APP_TEXT)
        await save_ui_state(session, ui_state, screen_message_id=message.message_id)
        logger.info(
            "ensure_screen_message: created message_id=%s for identity=%s chat_id=%s",
            message.message_id,
            user_id,
            chat_id,
        )
        return message.message_id


async def render_screen(
    bot: Bot,
    chat_id: int,
    user_id: int,
    session_factory: async_sessionmaker[AsyncSession],
    screen: str,
    payload: dict | None = None,
    push: bool = True,
) -> None:
    if screen not in SCREEN_NAMES:
        screen = HOME
    payload = payload or {}

    async with session_factory() as session:
        ui_state = await get_or_create_ui_state(session, user_id)
        stack = list(ui_state.stack or [])
        prev_screen = ui_state.current_screen
        prev_payload = dict(ui_state.payload or {})

        if push and (prev_screen != screen or prev_payload != payload):
            stack.append({"screen": prev_screen, "payload": prev_payload})

        await save_ui_state(
            session,
            ui_state,
            current_screen=screen,
            payload=payload,
            stack=stack,
        )
        message_id = ui_state.screen_message_id
        text, markup = await render_by_screen(
            session,
            user_id,
            screen,
            payload,
            include_back=bool(stack),
        )
        parse_mode = "HTML" if text.startswith("<pre>") else None

    if not message_id:
        message_id = await ensure_screen_message(bot, chat_id, user_id, session_factory)

    try:
        logger.info(
            "render_screen: editing message_id=%s chat_id=%s screen=%s identity=%s",
            message_id,
            chat_id,
            screen,
            user_id,
        )
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=markup,
            parse_mode=parse_mode,
        )
        return
    except TelegramBadRequest as exc:
        error_text = str(exc).lower()
        if "message is not modified" in error_text:
            return
        logger.warning(
            "render_screen: edit failed for identity=%s chat_id=%s message_id=%s error=%s; fallback to send_message",
            user_id,
            chat_id,
            message_id,
            exc,
        )
    except Exception:
        logger.exception(
            "render_screen: unexpected edit error for identity=%s chat_id=%s message_id=%s; fallback to send_message",
            user_id,
            chat_id,
            message_id,
        )

    logger.info(
        "render_screen: fallback send_message chat_id=%s screen=%s identity=%s",
        chat_id,
        screen,
        user_id,
    )
    message = await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=markup,
        parse_mode=parse_mode,
    )
    async with session_factory() as session:
        ui_state = await get_or_create_ui_state(session, user_id)
        previous_message_id = ui_state.screen_message_id
        await save_ui_state(session, ui_state, screen_message_id=message.message_id)
        logger.info(
            "render_screen: updated ui_state message_id from %s to %s for identity=%s",
            previous_message_id,
            message.message_id,
            user_id,
        )
    if previous_message_id and previous_message_id != message.message_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=int(previous_message_id))
        except TelegramBadRequest:
            # If message is already deleted/unavailable, ignore.
            pass


async def render_current_screen(
    bot: Bot,
    chat_id: int,
    user_id: int,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        ui_state = await get_or_create_ui_state(session, user_id)
        screen = ui_state.current_screen or HOME
        payload = dict(ui_state.payload or {})
    await render_screen(
        bot=bot,
        chat_id=chat_id,
        user_id=user_id,
        session_factory=session_factory,
        screen=screen,
        payload=payload,
        push=False,
    )


async def go_back(
    bot: Bot,
    chat_id: int,
    user_id: int,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        ui_state = await get_or_create_ui_state(session, user_id)
        stack = list(ui_state.stack or [])
        if not stack:
            screen = HOME
            payload: dict = {}
        else:
            previous = stack.pop()
            screen = str(previous.get("screen", HOME))
            payload = dict(previous.get("payload", {}))
        await save_ui_state(
            session,
            ui_state,
            current_screen=screen,
            payload=payload,
            stack=stack,
        )
    await render_screen(
        bot=bot,
        chat_id=chat_id,
        user_id=user_id,
        session_factory=session_factory,
        screen=screen,
        payload=payload,
        push=False,
    )
