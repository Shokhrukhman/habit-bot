from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Habit, HabitLog, HabitStatus
from src.services.habits import get_habit_by_id
from src.services.logs import get_daily_summary
from src.services.timezone import CURATED_TIMEZONES
from src.ui import strings as ui_str
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
    SNOOZE_CUSTOM_INPUT,
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
        kb.button(text=ui_str.BACK_BUTTON, callback_data="nav:back")
        if show_home:
            kb.button(text=ui_str.HOME_BUTTON, callback_data="nav:home")
            kb.adjust(2)
        else:
            kb.adjust(1)
    elif show_home:
        kb.button(text=ui_str.HOME_BUTTON, callback_data="nav:home")
        kb.adjust(1)
    return kb.as_markup()


async def render_home(session: AsyncSession, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    await get_user_by_telegram_id(session, user_id)
    kb = InlineKeyboardBuilder()
    kb.button(text=ui_str.HABITS_BUTTON, callback_data="nav:habits")
    kb.button(text=ui_str.STATS_BUTTON, callback_data="stats:open")
    kb.button(text=ui_str.SETTINGS_BUTTON, callback_data="nav:settings")
    kb.adjust(3)
    text = ui_str.HOME_TEXT
    return text, _with_nav(kb, with_back=False, show_home=False)


async def render_habits_menu(
    session: AsyncSession,
    user_id: int,
    include_back: bool = True,
) -> tuple[str, InlineKeyboardMarkup]:
    # Kept for backward compatibility; direct habits entry uses list screen.
    return await render_habits_list(session, user_id, include_back)


async def render_stats_menu(
    session: AsyncSession,
    user_id: int,
    include_back: bool = True,
) -> tuple[str, InlineKeyboardMarkup]:
    return await render_month(session, user_id, payload={}, include_back=include_back)


async def render_settings_menu(
    session: AsyncSession,
    user_id: int,
    include_back: bool = True,
) -> tuple[str, InlineKeyboardMarkup]:
    await get_user_by_telegram_id(session, user_id)
    kb = InlineKeyboardBuilder()
    kb.button(text=ui_str.TIMEZONE_BUTTON, callback_data="settings:timezone")
    kb.button(text="🔔 Notifications", callback_data="settings:notifications")
    kb.adjust(2)
    return ui_str.SETTINGS_TITLE, _with_nav(kb, with_back=include_back)


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
    text = ui_str.TIMEZONE_TEXT.format(current=current)
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
        label = f"✅ {minutes}m" if current == minutes else f"{minutes}m"
        if minutes >= 60:
            hours = minutes // 60
            suffix = "h"
            label = f"✅ {hours}{suffix}" if current == minutes else f"{hours}{suffix}"
        kb.button(text=label, callback_data=f"notif:snooze:{minutes}")
    kb.button(text=ui_str.CUSTOM_SNOOZE_BUTTON, callback_data="settings:snooze_custom")
    kb.adjust(3, 2, 1)
    text = ui_str.NOTIFICATION_TEXT.format(current=current)
    return text, _with_nav(kb, with_back=include_back)


async def render_snooze_custom_input(
    session: AsyncSession,
    user_id: int,
    include_back: bool = True,
) -> tuple[str, InlineKeyboardMarkup]:
    await get_user_by_telegram_id(session, user_id)
    kb = InlineKeyboardBuilder()
    text = ui_str.CUSTOM_SNOOZE_PROMPT
    return text, _with_nav(kb, with_back=include_back)


async def render_habits_list(
    session: AsyncSession, user_id: int, include_back: bool = True
) -> tuple[str, InlineKeyboardMarkup]:
    user = await get_user_by_telegram_id(session, user_id)
    kb = InlineKeyboardBuilder()
    if not user:
        text = ui_str.NO_HABITS_TEXT
        kb.button(text=ui_str.ADD_HABIT_BUTTON, callback_data="habit:add")
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
        kb.button(text=ui_str.NO_HABITS_PLACEHOLDER, callback_data="nav:habits")

    kb.button(text=ui_str.ADD_HABIT_BUTTON, callback_data="habit:add")
    kb.adjust(1)
    text = ui_str.MY_HABITS_TEXT
    return text, _with_nav(kb, with_back=include_back)


async def render_habit_view(
    session: AsyncSession, user_id: int, habit_id: int, include_back: bool = True
) -> tuple[str, InlineKeyboardMarkup]:
    habit = await get_habit_by_id(session, habit_id)
    kb = InlineKeyboardBuilder()
    if not habit or not habit.user or habit.user.telegram_id != user_id:
        text = ui_str.HABIT_NOT_FOUND
        kb.button(text=ui_str.HABITS_BUTTON, callback_data="habits:list")
        return text, _with_nav(kb, with_back=include_back)

    status = ui_str.STATUS_ACTIVE if habit.is_active else ui_str.STATUS_INACTIVE
    reminder = (
        min(habit.reminder_times, key=lambda item: item.time_local)
        if habit.reminder_times
        else None
    )
    time_text = reminder.time_local.strftime("%H:%M") if reminder else ui_str.TIME_NOT_SET
    lines = [ui_str.HABIT_VIEW_TEXT.format(title=habit.title, status=status, time=time_text)]

    toggle_text = ui_str.DEACTIVATE_BUTTON if habit.is_active else ui_str.ACTIVATE_BUTTON
    set_time_text = ui_str.CHANGE_TIME_BUTTON if reminder else ui_str.SET_TIME_BUTTON
    kb.button(text=toggle_text, callback_data=f"habit:toggle:{habit.id}")
    kb.button(text=set_time_text, callback_data=f"habit:add_time:{habit.id}")
    kb.adjust(2)
    return "\n".join(lines), _with_nav(kb, with_back=include_back)


async def render_habit_add(
    session: AsyncSession,
    user_id: int,
    include_back: bool = True,
) -> tuple[str, InlineKeyboardMarkup]:
    await get_user_by_telegram_id(session, user_id)
    kb = InlineKeyboardBuilder()
    text = ui_str.NEW_HABIT_TEXT
    return text, _with_nav(kb, with_back=include_back)


async def render_habit_add_time(
    session: AsyncSession,
    user_id: int,
    habit_id: int | None,
    include_back: bool = True,
) -> tuple[str, InlineKeyboardMarkup]:
    kb = InlineKeyboardBuilder()
    if not habit_id:
        text = ui_str.NO_HABIT_SELECTED
        kb.button(text=ui_str.HABITS_BUTTON, callback_data="habits:list")
        return text, _with_nav(kb, with_back=include_back)

    habit = await get_habit_by_id(session, habit_id)
    if not habit or not habit.user or habit.user.telegram_id != user_id:
        text = ui_str.HABIT_NOT_FOUND
        kb.button(text=ui_str.HABITS_BUTTON, callback_data="habits:list")
        return text, _with_nav(kb, with_back=include_back)

    reminder = (
        min(habit.reminder_times, key=lambda item: item.time_local)
        if habit.reminder_times
        else None
    )
    current = reminder.time_local.strftime("%H:%M") if reminder else ui_str.TIME_NOT_SET
    text = ui_str.SET_REMINDER_TIME_TEXT.format(title=habit.title, current=current)
    return text, _with_nav(kb, with_back=include_back)


async def render_today(
    session: AsyncSession,
    user_id: int,
    include_back: bool = True,
) -> tuple[str, InlineKeyboardMarkup]:
    user = await get_user_by_telegram_id(session, user_id)
    kb = InlineKeyboardBuilder()
    if not user:
        text = ui_str.TODAY_EMPTY
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
        text = ui_str.TODAY_EMPTY
        return text, _with_nav(kb, with_back=include_back)

    done_count = len(done)
    percent = int((done_count / total_count) * 100)
    filled_blocks = int((percent / 100) * 10)
    progress_bar = f"{'█' * filled_blocks}{'░' * (10 - filled_blocks)}"

    lines = [
        ui_str.TODAY_TITLE,
        f"{progress_bar} {percent}%",
        ui_str.DONE_PROGRESS.format(done=done_count, total=total_count),
    ]

    if done:
        lines.append("")
        lines.append(ui_str.DONE_SECTION)
        lines.extend([f"• {name}" for name in done])
    if skipped:
        lines.append("")
        lines.append(ui_str.SKIPPED_SECTION)
        lines.extend([f"• {name}" for name in skipped])
    if not_done:
        lines.append("")
        lines.append(ui_str.NOT_DONE_SECTION)
        lines.extend([f"• {name}" for name in not_done])

    return "\n".join(lines), _with_nav(kb, with_back=include_back)


_WEEKDAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _status_is_done(status: HabitStatus | str) -> bool:
    if isinstance(status, HabitStatus):
        return status.value == HabitStatus.DONE.value
    return str(status).lower() == HabitStatus.DONE.value


def _daterange(start_date: date, end_date: date) -> list[date]:
    days: list[date] = []
    current = start_date
    while current <= end_date:
        days.append(current)
        current += timedelta(days=1)
    return days


def _dot_bar(percent: int) -> str:
    filled = int((percent / 100) * 10)
    return f"{'●' * filled}{'○' * (10 - filled)}"


def _calendar_title(mode: str) -> str:
    if mode == "DETAILS":
        return ui_str.CALENDAR_DETAILS_TITLE
    return ui_str.CALENDAR_RANGE_TITLE


async def render_analytics_range(
    session: AsyncSession,
    user_id: int,
    start_date: date,
    end_date: date,
    include_back: bool = True,
) -> tuple[str, InlineKeyboardMarkup]:
    user = await get_user_by_telegram_id(session, user_id)
    kb = InlineKeyboardBuilder()
    kb.button(text=ui_str.CHOOSE_PERIOD_BUTTON, callback_data="stats:choose_period")
    kb.button(text=ui_str.DAY_DETAILS_BUTTON, callback_data="stats:day_details")
    kb.adjust(2)
    if not user:
        return ui_str.NO_DATA_PERIOD, _with_nav(kb, with_back=include_back)

    active_habits = list(
        await session.scalars(
            select(Habit)
            .where(and_(Habit.user_id == user.id, Habit.is_active.is_(True)))
            .order_by(Habit.title.asc())
        )
    )
    active_ids = [habit.id for habit in active_habits]
    planned = len(active_ids)

    done_by_day: dict[date, set[int]] = {}
    if active_ids:
        rows = await session.execute(
            select(HabitLog.local_date, HabitLog.habit_id, HabitLog.status).where(
                and_(
                    HabitLog.user_id == user.id,
                    HabitLog.local_date >= start_date,
                    HabitLog.local_date <= end_date,
                    HabitLog.habit_id.in_(active_ids),
                )
            )
        )
        for local_date, habit_id, status in rows.all():
            if _status_is_done(status):
                done_by_day.setdefault(local_date, set()).add(int(habit_id))

    raw_rows: list[tuple[date, str, int, int, int]] = []
    for day in _daterange(start_date, end_date):
        done_count = len(done_by_day.get(day, set()))
        percent = round(done_count / planned * 100) if planned > 0 else 0
        raw_rows.append((day, _dot_bar(percent), percent, done_count, planned))

    today = datetime.now(ZoneInfo(user.timezone)).date()
    length = (end_date - start_date).days + 1
    if length == 7 and end_date == today:
        header = "Last 7 days"
    elif start_date.year == end_date.year:
        header = f"{start_date.strftime('%b %d')}–{end_date.strftime('%b %d')}"
    else:
        header = f"{start_date.strftime('%b %d %Y')}–{end_date.strftime('%b %d %Y')}"

    lines: list[str] = [header]
    for day, _dot_bar_value, percent, done_count, planned_count in raw_rows:
        dow = _WEEKDAY_ABBR[day.weekday()]
        filled = int((percent / 100) * 10)
        bar = "●" * filled + "○" * (10 - filled)
        line = f"{dow:<3} {day.day:02d}  {bar}  {percent:>3}% │ {done_count:>2}/{planned_count:<2}".rstrip()
        lines.append(line)
    return "<pre>" + "\n".join(lines) + "</pre>", _with_nav(kb, with_back=include_back)


async def render_day_details(
    session: AsyncSession,
    user_id: int,
    target_date: date,
    include_back: bool = True,
) -> tuple[str, InlineKeyboardMarkup]:
    user = await get_user_by_telegram_id(session, user_id)
    kb = InlineKeyboardBuilder()
    if not user:
        return ui_str.NO_DATA_DAY, _with_nav(kb, with_back=include_back)

    active_habits = list(
        await session.scalars(
            select(Habit)
            .where(and_(Habit.user_id == user.id, Habit.is_active.is_(True)))
            .order_by(Habit.title.asc())
        )
    )
    planned = len(active_habits)
    active_ids = [habit.id for habit in active_habits]

    done_ids: set[int] = set()
    if active_ids:
        rows = await session.execute(
            select(HabitLog.habit_id, HabitLog.status).where(
                and_(
                    HabitLog.user_id == user.id,
                    HabitLog.local_date == target_date,
                    HabitLog.habit_id.in_(active_ids),
                )
            )
        )
        for habit_id, status in rows.all():
            if _status_is_done(status):
                done_ids.add(int(habit_id))

    done_titles = [habit.title for habit in active_habits if habit.id in done_ids]
    not_done_titles = [habit.title for habit in active_habits if habit.id not in done_ids]

    done_count = len(done_titles)
    percent = int((done_count / planned) * 100) if planned > 0 else 0
    lines = [
        f"📅 {_WEEKDAY_ABBR[target_date.weekday()]} {target_date.day:02d} {calendar.month_name[target_date.month]} {target_date.year}",
        f"Progress: {done_count}/{planned} ({percent}%)",
    ]
    if done_titles:
        lines.append("")
        lines.append("✅ Done:")
        lines.extend([f"• {title}" for title in done_titles])
    if not_done_titles:
        lines.append("")
        lines.append("❌ Not done:")
        lines.extend([f"• {title}" for title in not_done_titles])

    return "\n".join(lines), _with_nav(kb, with_back=include_back)


def _calendar_picker_markup(
    mode: str,
    month: int,
    year: int,
    selected_dates: list[date],
    include_back: bool,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for weekday in ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"):
        kb.button(text=weekday, callback_data="cal:noop")
    selected_index: dict[str, int] = {}
    for index, selected in enumerate(selected_dates, start=1):
        selected_index[selected.isoformat()] = index

    month_weeks = calendar.monthcalendar(year, month)
    for week in month_weeks:
        for day_value in week:
            if day_value == 0:
                kb.button(text=" ", callback_data="cal:noop")
                continue
            cell_date = date(year, month, day_value)
            marker = ""
            if mode == "RANGE":
                selected_marker = selected_index.get(cell_date.isoformat())
                if selected_marker == 1:
                    marker = "✓1"
                elif selected_marker == 2:
                    marker = "✓2"
            label = f"{day_value:02d}{marker}"
            kb.button(text=label, callback_data=f"cal:pick:{mode}:{cell_date.isoformat()}")

    kb.button(text="◀ Prev month", callback_data=f"cal:prev:{mode}")
    kb.button(text="Next month ▶", callback_data=f"cal:next:{mode}")
    if include_back:
        kb.button(text=ui_str.BACK_BUTTON, callback_data="nav:back")
        kb.button(text=ui_str.HOME_BUTTON, callback_data="nav:home")
        kb.adjust(7, *([7] * len(month_weeks)), 2, 2)
    else:
        kb.button(text=ui_str.HOME_BUTTON, callback_data="nav:home")
        kb.adjust(7, *([7] * len(month_weeks)), 2, 1)
    return kb.as_markup()


async def render_calendar_picker(
    session: AsyncSession,
    user_id: int,
    mode: str,
    month: int,
    year: int,
    selected_dates: list[date],
    include_back: bool = True,
) -> tuple[str, InlineKeyboardMarkup]:
    del session, user_id
    lines = [
        f"📅 {calendar.month_name[month]} {year}",
        _calendar_title(mode),
    ]
    if mode == "RANGE":
        first = selected_dates[0].isoformat() if len(selected_dates) >= 1 else "-"
        second = selected_dates[1].isoformat() if len(selected_dates) >= 2 else "-"
        lines.append(f"1: {first}")
        lines.append(f"2: {second}")
    text = "\n".join(lines)
    markup = _calendar_picker_markup(mode, month, year, selected_dates, include_back)
    return text, markup


async def render_month(
    session: AsyncSession,
    user_id: int,
    payload: dict | None = None,
    include_back: bool = True,
) -> tuple[str, InlineKeyboardMarkup]:
    user = await get_user_by_telegram_id(session, user_id)
    if not user:
        kb = InlineKeyboardBuilder()
        kb.button(text=ui_str.CHOOSE_PERIOD_BUTTON, callback_data="stats:choose_period")
        kb.button(text=ui_str.DAY_DETAILS_BUTTON, callback_data="stats:day_details")
        kb.adjust(2)
        return ui_str.NO_DATA_PERIOD, _with_nav(kb, with_back=include_back)

    payload = payload or {}
    tz = ZoneInfo(user.timezone)
    today = datetime.now(tz).date()
    start_date = today - timedelta(days=6)
    end_date = today
    start_raw = payload.get("start_date")
    end_raw = payload.get("end_date")
    if start_raw and end_raw:
        try:
            start_date = date.fromisoformat(str(start_raw))
            end_date = date.fromisoformat(str(end_raw))
        except ValueError:
            start_date = today - timedelta(days=6)
            end_date = today
    return await render_analytics_range(
        session,
        user_id,
        start_date,
        end_date,
        include_back=include_back,
    )


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
    if screen == SNOOZE_CUSTOM_INPUT:
        return await render_snooze_custom_input(session, user_id, include_back)
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
        return await render_month(session, user_id, payload, include_back)
    if screen == CALENDAR_PICKER:
        mode = str(payload.get("mode", "RANGE"))
        month = int(payload.get("month", datetime.now().month))
        year = int(payload.get("year", datetime.now().year))
        selected_dates: list[date] = []
        range_pick = payload.get("range_pick") or {}
        d1 = range_pick.get("d1")
        d2 = range_pick.get("d2")
        if d1:
            try:
                selected_dates.append(date.fromisoformat(str(d1)))
            except ValueError:
                pass
        if d2:
            try:
                selected_dates.append(date.fromisoformat(str(d2)))
            except ValueError:
                pass
        return await render_calendar_picker(
            session,
            user_id,
            mode,
            month,
            year,
            selected_dates,
            include_back,
        )
    if screen == DAY_DETAILS:
        raw_date = payload.get("date")
        if not raw_date:
            kb = InlineKeyboardBuilder()
            return ui_str.DATE_NOT_SELECTED, _with_nav(kb, with_back=include_back)
        try:
            target_date = date.fromisoformat(str(raw_date))
        except ValueError:
            kb = InlineKeyboardBuilder()
            return ui_str.INVALID_DATE, _with_nav(kb, with_back=include_back)
        return await render_day_details(session, user_id, target_date, include_back)
    return await render_home(session, user_id)
