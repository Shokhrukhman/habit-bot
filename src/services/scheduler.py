from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from src.db.models import Habit, User
from src.keyboards.habits import reminder_action_keyboard
from src.services.logs import finalize_day_not_done, get_daily_summary
from src.ui import strings as ui_str

logger = logging.getLogger(__name__)

_scheduler_instance: "HabitScheduler | None" = None


class HabitScheduler:
    def __init__(
        self,
        bot: Bot,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.bot = bot
        self.session_factory = session_factory
        self.scheduler = AsyncIOScheduler(timezone=UTC)

    async def start(self) -> None:
        self.scheduler.start()
        await self.schedule_all_users()
        logger.info("Scheduler started")

    async def shutdown(self) -> None:
        self.scheduler.shutdown(wait=False)

    async def schedule_all_users(self) -> None:
        async with self.session_factory() as session:
            users = list(await session.scalars(select(User)))
            for user in users:
                await self._reschedule_user_by_db_id(session, user.id)

    async def reschedule_user_by_telegram_id(self, telegram_id: int) -> None:
        async with self.session_factory() as session:
            user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
            if not user:
                return
            await self._reschedule_user_by_db_id(session, user.id)

    async def _reschedule_user_by_db_id(self, session: AsyncSession, user_id: int) -> None:
        user = await session.scalar(
            select(User)
            .options(
                selectinload(User.habits).selectinload(Habit.reminder_times),
            )
            .where(User.id == user_id)
        )
        if not user:
            return

        self._remove_jobs_with_prefix(f"reminder:{user.id}:")
        self._remove_job_if_exists(f"summary:{user.id}")
        self._schedule_summary(user.id, user.telegram_id, user.timezone)

        for habit in user.habits:
            if not habit.is_active:
                continue
            reminder = (
                min(habit.reminder_times, key=lambda item: item.time_local)
                if habit.reminder_times
                else None
            )
            if not reminder:
                continue
            self._schedule_reminder(
                user.id,
                habit.id,
                reminder.time_local.hour,
                reminder.time_local.minute,
                user.timezone,
            )

        logger.info("Rescheduled jobs for user_id=%s", user.id)

    def _schedule_reminder(
        self,
        user_id: int,
        habit_id: int,
        hour: int,
        minute: int,
        timezone: str,
    ) -> None:
        job_id = f"reminder:{user_id}:{habit_id}"
        self.scheduler.add_job(
            self.send_reminder_job,
            trigger=CronTrigger(hour=hour, minute=minute, second=0, timezone=timezone),
            args=[habit_id],
            id=job_id,
            replace_existing=True,
            coalesce=True,
            misfire_grace_time=120,
        )

    def _schedule_summary(self, user_id: int, telegram_id: int, timezone: str) -> None:
        job_id = f"summary:{user_id}"
        self.scheduler.add_job(
            self.send_daily_summary_job,
            trigger=CronTrigger(hour=23, minute=59, second=59, timezone=timezone),
            args=[user_id, telegram_id],
            id=job_id,
            replace_existing=True,
            coalesce=True,
            misfire_grace_time=300,
        )

    def _remove_jobs_with_prefix(self, prefix: str) -> None:
        for job in self.scheduler.get_jobs():
            if job.id.startswith(prefix):
                self.scheduler.remove_job(job.id)

    def _remove_job_if_exists(self, job_id: str) -> None:
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

    async def send_reminder_job(self, habit_id: int) -> None:
        async with self.session_factory() as session:
            habit = await session.scalar(
                select(Habit)
                .options(
                    selectinload(Habit.user),
                    selectinload(Habit.reminder_times),
                )
                .where(Habit.id == habit_id)
            )
            if not habit or not habit.user:
                return
            if not habit.is_active:
                return
            reminder = (
                min(habit.reminder_times, key=lambda item: item.time_local)
                if habit.reminder_times
                else None
            )
            if not reminder:
                return

            user = habit.user
            time_text = reminder.time_local.strftime("%H:%M")
            await self.bot.send_message(
                chat_id=user.telegram_id,
                text=f"🔔 {habit.title} — {time_text}",
                reply_markup=reminder_action_keyboard(habit.id),
            )

    async def send_daily_summary_job(self, user_id: int, telegram_id: int) -> None:
        async with self.session_factory() as session:
            user = await session.get(User, user_id)
            if not user:
                return
            await finalize_day_not_done(session, user)
            summary = await get_daily_summary(session, user)

            text = (
                f"{ui_str.DAILY_SUMMARY_TITLE}\n"
                f"✅ Done: {', '.join(summary.done) if summary.done else '-'}\n"
                f"❌ Not done: {', '.join(summary.not_done) if summary.not_done else '-'}\n"
                f"⏭ Skipped: {', '.join(summary.skipped) if summary.skipped else '-'}"
            )
            await self.bot.send_message(chat_id=telegram_id, text=text)

    async def schedule_snooze(self, telegram_id: int, habit_id: int) -> None:
        snooze_minutes = 10
        async with self.session_factory() as session:
            user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
            if user and user.snooze_minutes > 0:
                snooze_minutes = user.snooze_minutes
        run_at = datetime.now(UTC) + timedelta(minutes=snooze_minutes)
        # Keep one pending snooze per user+habit to prevent multi-click duplicates.
        job_id = f"snooze:{telegram_id}:{habit_id}"
        self.scheduler.add_job(
            self.send_snoozed_reminder_job,
            trigger=DateTrigger(run_date=run_at),
            args=[telegram_id, habit_id],
            id=job_id,
            replace_existing=True,
            misfire_grace_time=120,
        )

    async def send_snoozed_reminder_job(self, telegram_id: int, habit_id: int) -> None:
        async with self.session_factory() as session:
            habit = await session.scalar(
                select(Habit)
                .options(selectinload(Habit.user))
                .where(and_(Habit.id == habit_id, Habit.is_active.is_(True)))
            )
            if not habit or not habit.user:
                return
            await self.bot.send_message(
                chat_id=telegram_id,
                text=f"🔔 {habit.title} — Snooze",
                reply_markup=reminder_action_keyboard(habit.id),
            )


def set_scheduler_instance(instance: HabitScheduler) -> None:
    global _scheduler_instance
    _scheduler_instance = instance


def get_scheduler_instance() -> HabitScheduler:
    if not _scheduler_instance:
        raise RuntimeError("Scheduler is not initialized")
    return _scheduler_instance
