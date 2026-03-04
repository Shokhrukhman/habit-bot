from __future__ import annotations

import asyncio
import time
from datetime import datetime

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config import Settings
from src.db.models import Habit, HabitLog, HabitReminderTime, User
from src.services.scheduler import HabitScheduler

router = Router()
STARTED_AT = time.monotonic()


def _is_admin(message: Message, admin_id: int) -> bool:
    return bool(message.from_user and message.from_user.id == admin_id)


async def _require_admin(message: Message, admin_id: int) -> bool:
    if _is_admin(message, admin_id):
        return True
    await message.answer("Not allowed.")
    return False


def _format_uptime(seconds: float) -> str:
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


@router.message(Command("stats"))
async def admin_stats(
    message: Message,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if not await _require_admin(message, settings.admin_id):
        return
    async with session_factory() as session:
        users_count = int(await session.scalar(select(func.count()).select_from(User)) or 0)
        habits_count = int(await session.scalar(select(func.count()).select_from(Habit)) or 0)
        active_habits_count = int(
            await session.scalar(
                select(func.count()).select_from(Habit).where(Habit.is_active.is_(True))
            )
            or 0
        )
        reminders_count = int(
            await session.scalar(select(func.count()).select_from(HabitReminderTime)) or 0
        )
        logs_count = int(await session.scalar(select(func.count()).select_from(HabitLog)) or 0)
    text_out = (
        "Bot statistics\n"
        f"Users: {users_count}\n"
        f"Habits: {habits_count}\n"
        f"Active habits: {active_habits_count}\n"
        f"Reminder times: {reminders_count}\n"
        f"Habit logs: {logs_count}"
    )
    await message.answer(text_out)


@router.message(Command("users"))
async def admin_users(
    message: Message,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if not await _require_admin(message, settings.admin_id):
        return
    async with session_factory() as session:
        total = int(await session.scalar(select(func.count()).select_from(User)) or 0)
        rows = list(
            await session.scalars(select(User).order_by(User.created_at.desc()).limit(30))
        )
    lines = [f"Users total: {total}"]
    for user in rows:
        created = user.created_at
        created_text = created.strftime("%Y-%m-%d") if isinstance(created, datetime) else "-"
        lines.append(
            f"#{user.id} tg:{user.telegram_id} tz:{user.timezone} created:{created_text}"
        )
    if total > 30:
        lines.append(f"...and {total - 30} more")
    await message.answer("\n".join(lines))


@router.message(Command("broadcast"))
async def admin_broadcast(
    message: Message,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if not await _require_admin(message, settings.admin_id):
        return
    raw_text = (message.text or "").strip()
    parts = raw_text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Usage: /broadcast your message")
        return
    broadcast_text = parts[1].strip()
    async with session_factory() as session:
        telegram_ids = list(await session.scalars(select(User.telegram_id)))
    sent = 0
    failed = 0
    for tg_id in telegram_ids:
        try:
            await bot.send_message(chat_id=int(tg_id), text=broadcast_text)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    await message.answer(
        f"Broadcast finished\nSent: {sent}\nFailed: {failed}"
    )


@router.message(Command("health"))
async def admin_health(
    message: Message,
    session_factory: async_sessionmaker[AsyncSession],
    scheduler: HabitScheduler,
    settings: Settings,
) -> None:
    if not await _require_admin(message, settings.admin_id):
        return

    db_ok = False
    async with session_factory() as session:
        try:
            await session.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            db_ok = False

    postgres_status = "SKIPPED"
    try:
        process = await asyncio.create_subprocess_exec(
            "docker",
            "inspect",
            "-f",
            "{{.State.Status}}",
            "habit-bot-postgres",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=2.0)
        if process.returncode == 0:
            postgres_status = stdout.decode().strip() or "unknown"
        else:
            postgres_status = "SKIPPED"
    except Exception:
        postgres_status = "SKIPPED"

    uptime = _format_uptime(time.monotonic() - STARTED_AT)
    scheduler_ok = bool(scheduler and scheduler.scheduler)
    scheduler_text = "OK" if scheduler_ok else "NOT RUNNING"
    db_text = "OK" if db_ok else "FAILED"
    lines = [
        "Health",
        f"App: OK (uptime: {uptime})",
        f"DB: {db_text}",
        f"Scheduler: {scheduler_text}",
    ]
    if postgres_status != "SKIPPED":
        lines.append(f"Postgres container: {postgres_status}")
    await message.answer("\n".join(lines))
