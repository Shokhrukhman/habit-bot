from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date, datetime
from zoneinfo import ZoneInfo

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.db.models import HabitStatus
from src.services.habits import (
    delete_habit,
    get_habit_by_id,
    get_or_create_user,
    get_user_by_telegram_id,
    set_user_timezone,
)
from src.services.logs import upsert_habit_status
from src.services.scheduler import HabitScheduler
from src.services.timezone import is_valid_curated_timezone
from src.services.ui_state import (
    CALENDAR_PICKER,
    DAY_DETAILS,
    HABIT_ADD,
    HABIT_ADD_TIME,
    HABIT_VIEW,
    HABITS_MENU,
    HABITS_LIST,
    HOME,
    MONTH,
    NOTIFICATION_SETTINGS,
    SETTINGS_MENU,
    SNOOZE_CUSTOM_INPUT,
    TIMEZONE_SELECT,
    TODAY,
    get_or_create_ui_state,
)
from src.ui import strings as ui_str
from src.ui.navigation import go_back, render_current_screen, render_screen

router = Router()

CallbackHandler = Callable[
    [CallbackQuery, Bot, async_sessionmaker[AsyncSession], HabitScheduler, list[str]],
    Awaitable[None],
]


class CallbackRegistry:
    def __init__(self) -> None:
        self._exact: dict[str, CallbackHandler] = {}
        self._prefix: list[tuple[str, CallbackHandler]] = []

    def exact(self, key: str) -> Callable[[CallbackHandler], CallbackHandler]:
        def decorator(func: CallbackHandler) -> CallbackHandler:
            self._exact[key] = func
            return func

        return decorator

    def prefix(self, key: str) -> Callable[[CallbackHandler], CallbackHandler]:
        def decorator(func: CallbackHandler) -> CallbackHandler:
            self._prefix.append((key, func))
            return func

        return decorator

    async def dispatch(
        self,
        callback: CallbackQuery,
        bot: Bot,
        session_factory: async_sessionmaker[AsyncSession],
        scheduler: HabitScheduler,
    ) -> None:
        data = callback.data or ""
        parts = data.split(":")
        if data in self._exact:
            await self._exact[data](callback, bot, session_factory, scheduler, parts)
            return
        for prefix, handler in self._prefix:
            if data.startswith(prefix):
                await handler(callback, bot, session_factory, scheduler, parts)
                return
        await callback.answer(ui_str.ERROR_UNKNOWN_ACTION, show_alert=True)


registry = CallbackRegistry()


async def _delete_message_safe(bot: Bot, chat_id: int, message_id: int) -> None:
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramBadRequest:
        pass


def _callback_chat_id(callback: CallbackQuery) -> int:
    if callback.message:
        return callback.message.chat.id
    if callback.from_user:
        return callback.from_user.id
    raise ValueError("Cannot determine chat_id for callback")


async def _local_today(session: AsyncSession, telegram_id: int) -> date:
    user = await get_user_by_telegram_id(session, telegram_id)
    if not user:
        return datetime.now().date()
    return datetime.now(ZoneInfo(user.timezone)).date()


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    total = year * 12 + (month - 1) + delta
    new_year = total // 12
    new_month = (total % 12) + 1
    return new_year, new_month


@registry.exact("nav:home")
async def _nav_home(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    del scheduler, parts
    if not callback.from_user:
        return
    chat_id = _callback_chat_id(callback)
    await render_screen(
        bot=bot,
        chat_id=chat_id,
        user_id=callback.from_user.id,
        session_factory=session_factory,
        screen=HOME,
        payload={},
        push=False,
    )


@registry.exact("nav:open_app")
async def _nav_open_app(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    # Backward compatibility alias for old reminder button.
    await _nav_home(callback, bot, session_factory, scheduler, parts)


@registry.exact("nav:back")
async def _nav_back(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    del scheduler, parts
    if not callback.from_user:
        return
    chat_id = _callback_chat_id(callback)
    await go_back(bot, chat_id, callback.from_user.id, session_factory)


@registry.exact("nav:timezone")
async def _nav_timezone(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    del scheduler, parts
    if not callback.from_user:
        return
    chat_id = _callback_chat_id(callback)
    await render_screen(
        bot=bot,
        chat_id=chat_id,
        user_id=callback.from_user.id,
        session_factory=session_factory,
        screen=TIMEZONE_SELECT,
    )


@registry.exact("nav:habits")
async def _nav_habits(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    del scheduler, parts
    if not callback.from_user:
        return
    chat_id = _callback_chat_id(callback)
    await render_screen(
        bot=bot,
        chat_id=chat_id,
        user_id=callback.from_user.id,
        session_factory=session_factory,
        screen=HABITS_LIST,
    )


@registry.exact("nav:stats")
async def _nav_stats(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    await _stats_open(callback, bot, session_factory, scheduler, parts)


@registry.exact("nav:settings")
async def _nav_settings(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    del scheduler, parts
    if not callback.from_user:
        return
    chat_id = _callback_chat_id(callback)
    await render_screen(
        bot=bot,
        chat_id=chat_id,
        user_id=callback.from_user.id,
        session_factory=session_factory,
        screen=SETTINGS_MENU,
    )


@registry.exact("habits:list")
async def _habits_list(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    del scheduler, parts
    if not callback.from_user:
        return
    chat_id = _callback_chat_id(callback)
    await render_screen(
        bot=bot,
        chat_id=chat_id,
        user_id=callback.from_user.id,
        session_factory=session_factory,
        screen=HABITS_LIST,
    )


@registry.exact("stats:open")
async def _stats_open(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    del scheduler, parts
    if not callback.from_user:
        return
    chat_id = _callback_chat_id(callback)
    await render_screen(
        bot=bot,
        chat_id=chat_id,
        user_id=callback.from_user.id,
        session_factory=session_factory,
        screen=MONTH,
        payload={},
    )


@registry.exact("stats:month")
async def _stats_month_legacy(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    await _stats_open(callback, bot, session_factory, scheduler, parts)


@registry.exact("stats:day")
async def _stats_day_legacy(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    await _stats_day_details(callback, bot, session_factory, scheduler, parts)


@registry.exact("settings:timezone")
async def _settings_timezone(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    del scheduler, parts
    if not callback.from_user:
        return
    chat_id = _callback_chat_id(callback)
    await render_screen(
        bot=bot,
        chat_id=chat_id,
        user_id=callback.from_user.id,
        session_factory=session_factory,
        screen=TIMEZONE_SELECT,
    )


@registry.exact("settings:notifications")
async def _settings_notifications(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    del scheduler, parts
    if not callback.from_user:
        return
    chat_id = _callback_chat_id(callback)
    await render_screen(
        bot=bot,
        chat_id=chat_id,
        user_id=callback.from_user.id,
        session_factory=session_factory,
        screen=NOTIFICATION_SETTINGS,
    )


@registry.exact("settings:snooze_custom")
async def _settings_snooze_custom(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    del scheduler, parts
    if not callback.from_user:
        return
    chat_id = _callback_chat_id(callback)
    await render_screen(
        bot=bot,
        chat_id=chat_id,
        user_id=callback.from_user.id,
        session_factory=session_factory,
        screen=SNOOZE_CUSTOM_INPUT,
        payload={},
    )


@registry.prefix("notif:snooze:")
async def _settings_snooze_value(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    del scheduler
    if not callback.from_user or len(parts) != 3:
        return
    try:
        minutes = int(parts[2])
    except ValueError:
        await callback.answer(ui_str.ERROR_INVALID_VALUE, show_alert=True)
        return
    if minutes <= 0 or minutes > 24 * 60:
        await callback.answer(ui_str.ERROR_INVALID_RANGE_VALUE, show_alert=True)
        return
    async with session_factory() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        user.snooze_minutes = minutes
        await session.commit()
    await callback.answer(ui_str.SAVED_TEXT, show_alert=False)
    chat_id = _callback_chat_id(callback)
    await render_current_screen(bot, chat_id, callback.from_user.id, session_factory)


@registry.exact("nav:today")
async def _legacy_nav_today(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    await _stats_day_details(callback, bot, session_factory, scheduler, parts)


@registry.exact("nav:month")
async def _legacy_nav_month(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    await _stats_open(callback, bot, session_factory, scheduler, parts)


@registry.exact("stats:choose_period")
async def _stats_choose_period(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    del scheduler, parts
    if not callback.from_user:
        return
    chat_id = _callback_chat_id(callback)
    async with session_factory() as session:
        today = await _local_today(session, callback.from_user.id)
    await render_screen(
        bot=bot,
        chat_id=chat_id,
        user_id=callback.from_user.id,
        session_factory=session_factory,
        screen=CALENDAR_PICKER,
        payload={
            "mode": "RANGE",
            "month": today.month,
            "year": today.year,
            "range_pick": {"d1": None, "d2": None, "month": today.month, "year": today.year},
        },
    )


@registry.exact("stats:day_details")
async def _stats_day_details(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    del scheduler, parts
    if not callback.from_user:
        return
    chat_id = _callback_chat_id(callback)
    async with session_factory() as session:
        today = await _local_today(session, callback.from_user.id)
    await render_screen(
        bot=bot,
        chat_id=chat_id,
        user_id=callback.from_user.id,
        session_factory=session_factory,
        screen=CALENDAR_PICKER,
        payload={
            "mode": "DETAILS",
            "month": today.month,
            "year": today.year,
            "range_pick": {"d1": None, "d2": None, "month": today.month, "year": today.year},
        },
    )


@registry.exact("cal:noop")
async def _cal_noop(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    del callback, bot, session_factory, scheduler, parts
    return


@registry.prefix("cal:prev:")
async def _cal_prev(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    del scheduler
    if not callback.from_user or len(parts) != 3:
        return
    mode = parts[2]
    chat_id = _callback_chat_id(callback)
    async with session_factory() as session:
        ui_state = await get_or_create_ui_state(session, callback.from_user.id)
        payload = dict(ui_state.payload or {})
        year = int(payload.get("year", datetime.now().year))
        month = int(payload.get("month", datetime.now().month))
        year, month = _shift_month(year, month, -1)
        payload["year"] = year
        payload["month"] = month
        payload["mode"] = mode
        range_pick = dict(payload.get("range_pick") or {})
        range_pick["year"] = year
        range_pick["month"] = month
        payload["range_pick"] = range_pick
    await render_screen(
        bot=bot,
        chat_id=chat_id,
        user_id=callback.from_user.id,
        session_factory=session_factory,
        screen=CALENDAR_PICKER,
        payload=payload,
        push=False,
    )


@registry.prefix("cal:next:")
async def _cal_next(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    del scheduler
    if not callback.from_user or len(parts) != 3:
        return
    mode = parts[2]
    chat_id = _callback_chat_id(callback)
    async with session_factory() as session:
        ui_state = await get_or_create_ui_state(session, callback.from_user.id)
        payload = dict(ui_state.payload or {})
        year = int(payload.get("year", datetime.now().year))
        month = int(payload.get("month", datetime.now().month))
        year, month = _shift_month(year, month, 1)
        payload["year"] = year
        payload["month"] = month
        payload["mode"] = mode
        range_pick = dict(payload.get("range_pick") or {})
        range_pick["year"] = year
        range_pick["month"] = month
        payload["range_pick"] = range_pick
    await render_screen(
        bot=bot,
        chat_id=chat_id,
        user_id=callback.from_user.id,
        session_factory=session_factory,
        screen=CALENDAR_PICKER,
        payload=payload,
        push=False,
    )


@registry.prefix("cal:pick:")
async def _cal_pick(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    del scheduler
    if not callback.from_user or len(parts) != 4:
        return
    mode = parts[2]
    iso_date = parts[3]
    try:
        picked_date = date.fromisoformat(iso_date)
    except ValueError:
        await callback.answer(ui_str.ERROR_INVALID_DATE, show_alert=True)
        return

    chat_id = _callback_chat_id(callback)
    if mode == "DETAILS":
        await render_screen(
            bot=bot,
            chat_id=chat_id,
            user_id=callback.from_user.id,
            session_factory=session_factory,
            screen=DAY_DETAILS,
            payload={"date": picked_date.isoformat()},
        )
        return

    async with session_factory() as session:
        ui_state = await get_or_create_ui_state(session, callback.from_user.id)
        payload = dict(ui_state.payload or {})
        range_pick = dict(payload.get("range_pick") or {})
        d1 = range_pick.get("d1")
        d2 = range_pick.get("d2")
        if not d1:
            range_pick["d1"] = picked_date.isoformat()
            range_pick["d2"] = None
        elif not d2:
            range_pick["d2"] = picked_date.isoformat()
        else:
            range_pick["d1"] = picked_date.isoformat()
            range_pick["d2"] = None

        payload["mode"] = "RANGE"
        payload["month"] = picked_date.month
        payload["year"] = picked_date.year
        range_pick["month"] = picked_date.month
        range_pick["year"] = picked_date.year
        payload["range_pick"] = range_pick

    d1_value = range_pick.get("d1")
    d2_value = range_pick.get("d2")
    if not d1_value or not d2_value:
        await render_screen(
            bot=bot,
            chat_id=chat_id,
            user_id=callback.from_user.id,
            session_factory=session_factory,
            screen=CALENDAR_PICKER,
            payload=payload,
            push=False,
        )
        return

    first = date.fromisoformat(str(d1_value))
    second = date.fromisoformat(str(d2_value))
    start_date = min(first, second)
    end_date = max(first, second)
    length = (end_date - start_date).days + 1
    if length > 31:
        payload["range_pick"] = {
            "d1": None,
            "d2": None,
            "month": picked_date.month,
            "year": picked_date.year,
        }
        await callback.answer(
            ui_str.ERROR_RANGE_TOO_LARGE,
            show_alert=True,
        )
        await render_screen(
            bot=bot,
            chat_id=chat_id,
            user_id=callback.from_user.id,
            session_factory=session_factory,
            screen=CALENDAR_PICKER,
            payload=payload,
            push=False,
        )
        return

    await render_screen(
        bot=bot,
        chat_id=chat_id,
        user_id=callback.from_user.id,
        session_factory=session_factory,
        screen=MONTH,
        payload={
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
    )


@registry.prefix("tz:set:")
async def _timezone_set(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    if not callback.from_user or len(parts) < 3:
        return
    tz = ":".join(parts[2:])
    if not is_valid_curated_timezone(tz):
        await callback.answer(ui_str.ERROR_INVALID_TIMEZONE, show_alert=True)
        return
    async with session_factory() as session:
        await get_or_create_user(session, callback.from_user.id)
        await set_user_timezone(session, callback.from_user.id, tz)
    await scheduler.reschedule_user_by_telegram_id(callback.from_user.id)
    chat_id = _callback_chat_id(callback)
    await render_current_screen(bot, chat_id, callback.from_user.id, session_factory)


@registry.exact("habit:add")
async def _habit_add(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    del scheduler, parts
    if not callback.from_user:
        return
    chat_id = _callback_chat_id(callback)
    await render_screen(
        bot=bot,
        chat_id=chat_id,
        user_id=callback.from_user.id,
        session_factory=session_factory,
        screen=HABIT_ADD,
    )


@registry.prefix("habit:view:")
async def _habit_view(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    del scheduler
    if not callback.from_user or len(parts) != 3:
        return
    habit_id = int(parts[2])
    chat_id = _callback_chat_id(callback)
    await render_screen(
        bot=bot,
        chat_id=chat_id,
        user_id=callback.from_user.id,
        session_factory=session_factory,
        screen=HABIT_VIEW,
        payload={"habit_id": habit_id},
    )


@registry.prefix("habit:delete:")
async def _habit_delete(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    if not callback.from_user or len(parts) != 3:
        return
    habit_id = int(parts[2])
    async with session_factory() as session:
        habit = await get_habit_by_id(session, habit_id)
        if not habit or not habit.user or habit.user.telegram_id != callback.from_user.id:
            await callback.answer(ui_str.ERROR_NO_ACCESS, show_alert=True)
            return
        await delete_habit(session, habit_id)
    await scheduler.reschedule_user_by_telegram_id(callback.from_user.id)
    chat_id = _callback_chat_id(callback)
    await render_screen(
        bot=bot,
        chat_id=chat_id,
        user_id=callback.from_user.id,
        session_factory=session_factory,
        screen=HABITS_LIST,
        payload={},
        push=False,
    )


@registry.prefix("habit:toggle:")
async def _habit_toggle_legacy(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    await _habit_delete(callback, bot, session_factory, scheduler, parts)


@registry.prefix("habit:add_time:")
async def _habit_add_time(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    del scheduler
    if not callback.from_user or len(parts) != 3:
        return
    habit_id = int(parts[2])
    chat_id = _callback_chat_id(callback)
    await render_screen(
        bot=bot,
        chat_id=chat_id,
        user_id=callback.from_user.id,
        session_factory=session_factory,
        screen=HABIT_ADD_TIME,
        payload={"habit_id": habit_id},
    )


@registry.prefix("today:done:")
async def _today_done(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    del scheduler
    await _today_action(callback, bot, session_factory, parts, HabitStatus.DONE)


@registry.prefix("today:skip:")
async def _today_skip(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    del scheduler
    await _today_action(callback, bot, session_factory, parts, HabitStatus.SKIP)


@registry.prefix("today:snooze:")
async def _today_snooze(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    if not callback.from_user or len(parts) != 3:
        return
    habit_id = int(parts[2])
    await scheduler.schedule_snooze(callback.from_user.id, habit_id)
    chat_id = _callback_chat_id(callback)
    await render_current_screen(bot, chat_id, callback.from_user.id, session_factory)


async def _today_action(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    parts: list[str],
    status: HabitStatus,
) -> None:
    if not callback.from_user or len(parts) != 3:
        return
    try:
        habit_id = int(parts[2])
    except ValueError:
        await callback.answer(ui_str.ERROR_INVALID_HABIT_ID, show_alert=True)
        return
    async with session_factory() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        habit = await get_habit_by_id(session, habit_id)
        if not user or not habit or habit.user_id != user.id:
            await callback.answer(ui_str.ERROR_NO_ACCESS, show_alert=True)
            return
        await upsert_habit_status(session, user, habit, status)
    chat_id = _callback_chat_id(callback)
    await render_current_screen(bot, chat_id, callback.from_user.id, session_factory)


@registry.prefix("reminder:done:")
async def _legacy_reminder_done(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    del scheduler
    await _today_action(callback, bot, session_factory, parts, HabitStatus.DONE)


@registry.prefix("reminder:skip:")
async def _legacy_reminder_skip(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    del scheduler
    await _today_action(callback, bot, session_factory, parts, HabitStatus.SKIP)


@registry.prefix("reminder:snooze:")
async def _legacy_reminder_snooze(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    parts: list[str],
) -> None:
    if not callback.from_user or len(parts) != 3:
        return
    try:
        habit_id = int(parts[2])
    except ValueError:
        await callback.answer(ui_str.ERROR_INVALID_HABIT_ID, show_alert=True)
        return
    await scheduler.schedule_snooze(callback.from_user.id, habit_id)
    chat_id = _callback_chat_id(callback)
    await render_current_screen(bot, chat_id, callback.from_user.id, session_factory)


@router.callback_query(F.data)
async def callbacks_dispatcher(
    callback: CallbackQuery,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
) -> None:
    await registry.dispatch(callback, bot, session_factory, scheduler)

    if callback.from_user and callback.message:
        async with session_factory() as session:
            ui_state = await get_or_create_ui_state(session, callback.from_user.id)
            active_screen_message_id = ui_state.screen_message_id
        if (
            active_screen_message_id
            and callback.message.message_id != int(active_screen_message_id)
        ):
            await _delete_message_safe(
                bot=bot,
                chat_id=_callback_chat_id(callback),
                message_id=callback.message.message_id,
            )

    try:
        await callback.answer()
    except TelegramBadRequest:
        # Callback may already be answered inside handler (e.g. show_alert).
        pass
