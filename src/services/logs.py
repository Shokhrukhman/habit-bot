from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models import Habit, HabitLog, HabitStatus, User


@dataclass(slots=True)
class DailySummary:
    done: list[str]
    skipped: list[str]
    not_done: list[str]


def local_today(tz_name: str) -> date:
    return datetime.now(ZoneInfo(tz_name)).date()


def _status_value(status: HabitStatus | str) -> str:
    if isinstance(status, HabitStatus):
        return status.value
    return str(status).lower()


async def upsert_habit_status(
    session: AsyncSession,
    user: User,
    habit: Habit,
    status: HabitStatus,
    target_date: date | None = None,
) -> HabitLog:
    local_date = target_date or local_today(user.timezone)
    status_value = status.value
    stmt = select(HabitLog).where(
        and_(
            HabitLog.user_id == user.id,
            HabitLog.habit_id == habit.id,
            HabitLog.local_date == local_date,
        )
    )
    log = await session.scalar(stmt)
    if not log:
        log = HabitLog(
            user_id=user.id,
            habit_id=habit.id,
            local_date=local_date,
            status=status_value,
            done_at_utc=datetime.now(UTC) if status == HabitStatus.DONE else None,
        )
        session.add(log)
    else:
        log.status = status_value
        log.done_at_utc = datetime.now(UTC) if status == HabitStatus.DONE else None
    await session.commit()
    await session.refresh(log)
    return log


async def get_daily_summary(
    session: AsyncSession, user: User, target_date: date | None = None
) -> DailySummary:
    local_date = target_date or local_today(user.timezone)
    habit_stmt = select(Habit).where(
        and_(Habit.user_id == user.id, Habit.is_active.is_(True))
    )
    habits = list(await session.scalars(habit_stmt))
    if not habits:
        return DailySummary(done=[], skipped=[], not_done=[])

    log_stmt = (
        select(HabitLog)
        .options(selectinload(HabitLog.habit))
        .where(and_(HabitLog.user_id == user.id, HabitLog.local_date == local_date))
    )
    logs = list(await session.scalars(log_stmt))
    by_habit = {log.habit_id: log for log in logs}

    done: list[str] = []
    skipped: list[str] = []
    not_done: list[str] = []

    for habit in habits:
        log = by_habit.get(habit.id)
        if not log:
            not_done.append(habit.title)
            continue
        status_value = _status_value(log.status)
        if status_value == HabitStatus.DONE.value:
            done.append(habit.title)
        elif status_value == HabitStatus.SKIP.value:
            skipped.append(habit.title)
        else:
            not_done.append(habit.title)

    return DailySummary(done=done, skipped=skipped, not_done=not_done)


async def finalize_day_not_done(
    session: AsyncSession, user: User, target_date: date | None = None
) -> None:
    local_date = target_date or local_today(user.timezone)
    habit_stmt = select(Habit).where(
        and_(Habit.user_id == user.id, Habit.is_active.is_(True))
    )
    habits = list(await session.scalars(habit_stmt))
    if not habits:
        return

    log_stmt = select(HabitLog).where(
        and_(HabitLog.user_id == user.id, HabitLog.local_date == local_date)
    )
    logs = list(await session.scalars(log_stmt))
    existing = {log.habit_id for log in logs}

    for habit in habits:
        if habit.id in existing:
            continue
        session.add(
            HabitLog(
                user_id=user.id,
                habit_id=habit.id,
                local_date=local_date,
                status=HabitStatus.NOT_DONE.value,
                done_at_utc=None,
            )
        )
    await session.commit()


async def month_status_map(session: AsyncSession, user: User, year: int, month: int) -> dict[int, str]:
    habit_stmt = select(Habit).where(
        and_(Habit.user_id == user.id, Habit.is_active.is_(True))
    )
    active_habits = list(await session.scalars(habit_stmt))
    active_count = len(active_habits)

    first_day = date(year, month, 1)
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)

    log_stmt = (
        select(HabitLog)
        .where(
            and_(
                HabitLog.user_id == user.id,
                HabitLog.local_date >= first_day,
                HabitLog.local_date < next_month,
            )
        )
        .order_by(HabitLog.local_date.asc())
    )
    logs = list(await session.scalars(log_stmt))
    by_day: dict[int, list[HabitLog]] = defaultdict(list)
    for log in logs:
        by_day[log.local_date.day].append(log)

    result: dict[int, str] = {}
    for day, day_logs in by_day.items():
        done_count = sum(
            1 for item in day_logs if _status_value(item.status) == HabitStatus.DONE.value
        )
        touched_count = sum(
            1
            for item in day_logs
            if _status_value(item.status) in (HabitStatus.DONE.value, HabitStatus.SKIP.value)
        )

        if active_count > 0 and done_count >= active_count:
            result[day] = "✅"
        elif touched_count > 0:
            result[day] = "⚠️"
        else:
            result[day] = "❌"
    return result
