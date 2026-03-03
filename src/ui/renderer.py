from __future__ import annotations

import calendar
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Habit
from src.services.habits import get_habit_by_id
from src.services.logs import get_daily_summary, month_status_map
from src.services.timezone import CURATED_TIMEZONES
from src.services.ui_state import (
    HABIT_ADD,
    HABIT_ADD_TIME,
    HABIT_VIEW,
    HABITS_MENU,
    HABITS_LIST,
    HOME,
    MONTH,
    NOTIFICATION_SETTINGS,
    SETTINGS_MENU,
    STATS_MENU,
    TIMEZONE_SELECT,
    TODAY,
    get_user_by_telegram_id,
)


def _with_nav(
    kb: InlineKeyboardBuilder,
    with_back: bool,
    show_home: bool = True,
) -> InlineKeyboardMarkup:
    if with_back:
        kb.button(text="⬅️ Back", callback_data="nav:back")
        if show_home:
            kb.button(text="🏠 Home", callback_data="nav:home")
            kb.adjust(2)
        else:
            kb.adjust(1)
    elif show_home:
        kb.button(text="🏠 Home", callback_data="nav:home")
        kb.adjust(1)
    return kb.as_markup()


async def render_home(session: AsyncSession, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    await get_user_by_telegram_id(session, user_id)
    kb = InlineKeyboardBuilder()
    kb.button(text="📚 Привычки", callback_data="nav:habits")
    kb.button(text="📊 Статистика", callback_data="nav:stats")
    kb.button(text="⚙️ Настройки", callback_data="nav:settings")
    kb.adjust(3)
    text = "Привет! Это твой habit app.\nВыбери раздел:"
    return text, _with_nav(kb, with_back=False, show_home=False)


async def render_habits_menu(
    session: AsyncSession,
    user_id: int,
    include_back: bool = True,
) -> tuple[str, InlineKeyboardMarkup]:
    await get_user_by_telegram_id(session, user_id)
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Список привычек", callback_data="habits:list")
    kb.button(text="➕ Добавить привычку", callback_data="habit:add")
    kb.adjust(2)
    return "📚 Привычки", _with_nav(kb, with_back=include_back)


async def render_stats_menu(
    session: AsyncSession,
    user_id: int,
    include_back: bool = True,
) -> tuple[str, InlineKeyboardMarkup]:
    await get_user_by_telegram_id(session, user_id)
    kb = InlineKeyboardBuilder()
    kb.button(text="📅 Месяц", callback_data="stats:month")
    kb.button(text="✅ День", callback_data="stats:day")
    kb.adjust(2)
    return "📊 Статистика", _with_nav(kb, with_back=include_back)


async def render_settings_menu(
    session: AsyncSession,
    user_id: int,
    include_back: bool = True,
) -> tuple[str, InlineKeyboardMarkup]:
    await get_user_by_telegram_id(session, user_id)
    kb = InlineKeyboardBuilder()
    kb.button(text="🕒 Таймзона", callback_data="settings:timezone")
    kb.button(text="🔔 Уведомления", callback_data="settings:notifications")
    kb.adjust(2)
    return "⚙️ Настройки", _with_nav(kb, with_back=include_back)


async def render_timezone_select(
    session: AsyncSession,
    user_id: int,
    include_back: bool = True,
) -> tuple[str, InlineKeyboardMarkup]:
    user = await get_user_by_telegram_id(session, user_id)
    current = user.timezone if user else "Asia/Tashkent"
    kb = InlineKeyboardBuilder()
    for tz in CURATED_TIMEZONES:
        marker = "✅ " if tz == current else ""
        kb.button(text=f"{marker}{tz}", callback_data=f"tz:set:{tz}")
    kb.adjust(1)
    text = f"🕒 Часовой пояс\nТекущий: {current}\n\nВыбери из списка:"
    return text, _with_nav(kb, with_back=include_back)


async def render_notification_settings(
    session: AsyncSession,
    user_id: int,
    include_back: bool = True,
) -> tuple[str, InlineKeyboardMarkup]:
    user = await get_user_by_telegram_id(session, user_id)
    current = user.snooze_minutes if user else 10
    kb = InlineKeyboardBuilder()
    options = [10, 15, 30, 60, 120]
    for minutes in options:
        label = f"✅ {minutes}м" if current == minutes else f"{minutes}м"
        if minutes >= 60:
            hours = minutes // 60
            suffix = "ч" if hours == 1 else "ч"
            label = f"✅ {hours}{suffix}" if current == minutes else f"{hours}{suffix}"
        kb.button(text=label, callback_data=f"notif:snooze:{minutes}")
    kb.adjust(3, 2)
    text = (
        "🔔 Настройки уведомлений\n"
        f"Текущий snooze: {current} минут\n"
        "Выбери задержку snooze:"
    )
    return text, _with_nav(kb, with_back=include_back)


async def render_habits_list(
    session: AsyncSession, user_id: int, include_back: bool = True
) -> tuple[str, InlineKeyboardMarkup]:
    user = await get_user_by_telegram_id(session, user_id)
    kb = InlineKeyboardBuilder()
    if not user:
        text = "Пока нет привычек."
        kb.button(text="➕ Add habit", callback_data="habit:add")
        return text, _with_nav(kb, with_back=include_back)

    habits = list(
        await session.scalars(
            select(Habit).where(Habit.user_id == user.id).order_by(Habit.id.asc())
        )
    )
    if habits:
        for habit in habits:
            marker = "🟢" if habit.is_active else "⚪"
            kb.button(text=f"{marker} {habit.title}", callback_data=f"habit:view:{habit.id}")
    else:
        kb.button(text="— Нет привычек —", callback_data="nav:habits")

    kb.button(text="➕ Add habit", callback_data="habit:add")
    kb.adjust(1)
    text = "📋 Мои привычки"
    return text, _with_nav(kb, with_back=include_back)


async def render_habit_view(
    session: AsyncSession, user_id: int, habit_id: int, include_back: bool = True
) -> tuple[str, InlineKeyboardMarkup]:
    habit = await get_habit_by_id(session, habit_id)
    kb = InlineKeyboardBuilder()
    if not habit or not habit.user or habit.user.telegram_id != user_id:
        text = "Привычка не найдена."
        kb.button(text="📋 Список привычек", callback_data="habits:list")
        return text, _with_nav(kb, with_back=include_back)

    status = "активна" if habit.is_active else "неактивна"
    times = sorted(habit.reminder_times, key=lambda item: item.time_local)
    lines = [f"🧩 {habit.title}", f"Статус: {status}", "Времена:"]
    if times:
        for t in times:
            lines.append(f"- {t.time_local.strftime('%H:%M')}")
    else:
        lines.append("- нет")

    toggle_text = "⏸ Deactivate" if habit.is_active else "▶️ Activate"
    kb.button(text=toggle_text, callback_data=f"habit:toggle:{habit.id}")
    kb.button(text="➕ Add time", callback_data=f"habit:add_time:{habit.id}")
    for t in times:
        kb.button(text=f"🗑 {t.time_local.strftime('%H:%M')}", callback_data=f"habit:del_time:{t.id}")
    kb.adjust(2, 1)
    return "\n".join(lines), _with_nav(kb, with_back=include_back)


async def render_habit_add(
    session: AsyncSession,
    user_id: int,
    include_back: bool = True,
) -> tuple[str, InlineKeyboardMarkup]:
    await get_user_by_telegram_id(session, user_id)
    kb = InlineKeyboardBuilder()
    text = "➕ Новая привычка\nОтправь название текстом."
    return text, _with_nav(kb, with_back=include_back)


async def render_habit_add_time(
    session: AsyncSession,
    user_id: int,
    habit_id: int | None,
    include_back: bool = True,
) -> tuple[str, InlineKeyboardMarkup]:
    kb = InlineKeyboardBuilder()
    if not habit_id:
        text = "Не выбрана привычка. Открой привычку и нажми Add time."
        kb.button(text="📋 Список привычек", callback_data="habits:list")
        return text, _with_nav(kb, with_back=include_back)

    habit = await get_habit_by_id(session, habit_id)
    if not habit or not habit.user or habit.user.telegram_id != user_id:
        text = "Привычка не найдена."
        kb.button(text="📋 Список привычек", callback_data="habits:list")
        return text, _with_nav(kb, with_back=include_back)

    text = f"🕒 Добавление времени\nПривычка: {habit.title}\nОтправь время в формате HH:MM."
    return text, _with_nav(kb, with_back=include_back)


async def render_today(
    session: AsyncSession,
    user_id: int,
    include_back: bool = True,
) -> tuple[str, InlineKeyboardMarkup]:
    user = await get_user_by_telegram_id(session, user_id)
    kb = InlineKeyboardBuilder()
    if not user:
        text = "📅 Сегодня\nНет активных привычек."
        return text, _with_nav(kb, with_back=include_back)

    summary = await get_daily_summary(session, user)
    def _unique(items: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            result.append(item)
        return result

    done = _unique(summary.done)
    skipped = _unique(summary.skipped)
    not_done = _unique(summary.not_done)

    total_count = len(done) + len(skipped) + len(not_done)
    if total_count == 0:
        text = "📅 Сегодня\nНет активных привычек."
        return text, _with_nav(kb, with_back=include_back)

    done_count = len(done)
    percent = int((done_count / total_count) * 100)
    filled_blocks = int((percent / 100) * 10)
    progress_bar = f"{'█' * filled_blocks}{'░' * (10 - filled_blocks)}"

    lines = [
        "📅 Сегодня",
        f"{progress_bar} {percent}%",
        f"{done_count} из {total_count} выполнено",
    ]

    if done:
        lines.append("")
        lines.append("✅ Выполнено:")
        lines.extend([f"• {name}" for name in done])
    if skipped:
        lines.append("")
        lines.append("⏭ Пропущено:")
        lines.extend([f"• {name}" for name in skipped])
    if not_done:
        lines.append("")
        lines.append("❌ Не выполнено:")
        lines.extend([f"• {name}" for name in not_done])

    return "\n".join(lines), _with_nav(kb, with_back=include_back)


async def render_month(
    session: AsyncSession,
    user_id: int,
    include_back: bool = True,
) -> tuple[str, InlineKeyboardMarkup]:
    user = await get_user_by_telegram_id(session, user_id)
    kb = InlineKeyboardBuilder()
    if not user:
        return "📅 Нет данных за месяц.", _with_nav(kb, with_back=include_back)
    now_local = datetime.now(ZoneInfo(user.timezone))
    statuses = await month_status_map(session, user, now_local.year, now_local.month)
    days_in_month = calendar.monthrange(now_local.year, now_local.month)[1]
    lines = [f"📅 {now_local.year:04d}-{now_local.month:02d}"]
    for day in range(1, days_in_month + 1):
        lines.append(f"{day:02d} {statuses.get(day, '❌')}")
    return "\n".join(lines), _with_nav(kb, with_back=include_back)


async def render_by_screen(
    session: AsyncSession,
    user_id: int,
    screen: str,
    payload: dict,
    include_back: bool,
) -> tuple[str, InlineKeyboardMarkup]:
    if screen == HOME:
        return await render_home(session, user_id)
    if screen == HABITS_MENU:
        return await render_habits_menu(session, user_id, include_back)
    if screen == STATS_MENU:
        return await render_stats_menu(session, user_id, include_back)
    if screen == SETTINGS_MENU:
        return await render_settings_menu(session, user_id, include_back)
    if screen == TIMEZONE_SELECT:
        return await render_timezone_select(session, user_id, include_back)
    if screen == NOTIFICATION_SETTINGS:
        return await render_notification_settings(session, user_id, include_back)
    if screen == HABITS_LIST:
        return await render_habits_list(session, user_id, include_back)
    if screen == HABIT_VIEW:
        return await render_habit_view(
            session, user_id, int(payload.get("habit_id", 0)), include_back
        )
    if screen == HABIT_ADD:
        return await render_habit_add(session, user_id, include_back)
    if screen == HABIT_ADD_TIME:
        habit_id = payload.get("habit_id")
        return await render_habit_add_time(
            session,
            user_id,
            int(habit_id) if habit_id else None,
            include_back,
        )
    if screen == TODAY:
        return await render_today(session, user_id, include_back)
    if screen == MONTH:
        return await render_month(session, user_id, include_back)
    return await render_home(session, user_id)
