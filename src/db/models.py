from __future__ import annotations

from datetime import date, datetime, time
from enum import Enum as PyEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


class HabitStatus(str, PyEnum):
    DONE = "done"
    SKIP = "skip"
    NOT_DONE = "not_done"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Tashkent")
    snooze_minutes: Mapped[int] = mapped_column(default=10)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    habits: Mapped[list["Habit"]] = relationship(back_populates="user")
    ui_state: Mapped["UiState | None"] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )


class Habit(Base):
    __tablename__ = "habits"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(140))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="habits")
    reminder_times: Mapped[list["HabitReminderTime"]] = relationship(
        back_populates="habit", cascade="all, delete-orphan"
    )
    logs: Mapped[list["HabitLog"]] = relationship(back_populates="habit")


class HabitReminderTime(Base):
    __tablename__ = "habit_reminder_times"
    __table_args__ = (UniqueConstraint("habit_id", "time_local", name="uq_habit_time"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    habit_id: Mapped[int] = mapped_column(ForeignKey("habits.id", ondelete="CASCADE"))
    time_local: Mapped[time] = mapped_column(Time(timezone=False))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    habit: Mapped["Habit"] = relationship(back_populates="reminder_times")


class HabitLog(Base):
    __tablename__ = "habit_logs"
    __table_args__ = (
        UniqueConstraint("user_id", "habit_id", "local_date", name="uq_user_habit_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    habit_id: Mapped[int] = mapped_column(ForeignKey("habits.id", ondelete="CASCADE"))
    local_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[HabitStatus] = mapped_column(
        Enum(
            HabitStatus,
            name="habit_status",
            native_enum=True,
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        default=HabitStatus.NOT_DONE,
    )
    done_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    habit: Mapped["Habit"] = relationship(back_populates="logs")


class UiState(Base):
    __tablename__ = "ui_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    screen_message_id: Mapped[int | None] = mapped_column(BigInteger)
    current_screen: Mapped[str] = mapped_column(String(64), default="HOME")
    stack: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="ui_state")
