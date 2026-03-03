from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models import Habit, HabitReminderTime, User


@dataclass(slots=True)
class HabitWithTimes:
    habit: Habit
    times: list[HabitReminderTime]


async def get_or_create_user(session: AsyncSession, telegram_id: int) -> User:
    stmt: Select[tuple[User]] = select(User).where(User.telegram_id == telegram_id)
    user = await session.scalar(stmt)
    if user:
        return user
    user = User(telegram_id=telegram_id)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def set_user_timezone(session: AsyncSession, telegram_id: int, timezone: str) -> User:
    user = await get_or_create_user(session, telegram_id)
    user.timezone = timezone
    await session.commit()
    await session.refresh(user)
    return user


async def set_user_snooze_minutes(
    session: AsyncSession,
    telegram_id: int,
    snooze_minutes: int,
) -> User:
    user = await get_or_create_user(session, telegram_id)
    user.snooze_minutes = snooze_minutes
    await session.commit()
    await session.refresh(user)
    return user


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    stmt: Select[tuple[User]] = select(User).where(User.telegram_id == telegram_id)
    return await session.scalar(stmt)


async def create_habit(session: AsyncSession, telegram_id: int, title: str) -> Habit:
    user = await get_or_create_user(session, telegram_id)
    habit = Habit(user_id=user.id, title=title.strip(), is_active=True)
    session.add(habit)
    await session.commit()
    await session.refresh(habit)
    return habit


async def get_habits_for_user(
    session: AsyncSession, telegram_id: int, include_inactive: bool = True
) -> list[Habit]:
    user = await get_user_by_telegram_id(session, telegram_id)
    if not user:
        return []
    stmt = (
        select(Habit)
        .options(selectinload(Habit.reminder_times))
        .where(Habit.user_id == user.id)
        .order_by(Habit.id.asc())
    )
    if not include_inactive:
        stmt = stmt.where(Habit.is_active.is_(True))
    result = await session.scalars(stmt)
    return list(result)


async def get_habit_by_id(session: AsyncSession, habit_id: int) -> Habit | None:
    stmt = (
        select(Habit)
        .options(selectinload(Habit.reminder_times), selectinload(Habit.user))
        .where(Habit.id == habit_id)
    )
    return await session.scalar(stmt)


async def set_habit_time(
    session: AsyncSession, habit_id: int, local_time: time
) -> HabitReminderTime:
    reminders = list(
        await session.scalars(
            select(HabitReminderTime).where(HabitReminderTime.habit_id == habit_id)
        )
    )
    if not reminders:
        reminder = HabitReminderTime(habit_id=habit_id, time_local=local_time)
        session.add(reminder)
    else:
        reminder = min(reminders, key=lambda item: item.time_local)
        reminder.time_local = local_time
        for extra in reminders:
            if extra.id != reminder.id:
                await session.delete(extra)
    await session.commit()
    await session.refresh(reminder)
    return reminder


async def set_habit_active(session: AsyncSession, habit_id: int, active: bool) -> Habit | None:
    habit = await session.get(Habit, habit_id)
    if not habit:
        return None
    habit.is_active = active
    await session.commit()
    await session.refresh(habit)
    return habit


async def delete_habit(session: AsyncSession, habit_id: int) -> Habit | None:
    habit = await session.get(Habit, habit_id)
    if not habit:
        return None
    habit.is_active = False
    await session.commit()
    await session.refresh(habit)
    return habit
