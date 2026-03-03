"""init habit tracker tables

Revision ID: 20260303_0001
Revises: None
Create Date: 2026-03-03 11:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260303_0001"
down_revision = None
branch_labels = None
depends_on = None


# ✅ Use existing ENUM type, never auto-create it from table hooks
habit_status = postgresql.ENUM(
    "done", "skip", "not_done",
    name="habit_status",
    create_type=False,
)


def upgrade() -> None:
    # ✅ Create ENUM once in an idempotent way
    op.execute("""
    DO $$
    BEGIN
        CREATE TYPE habit_status AS ENUM ('done', 'skip', 'not_done');
    EXCEPTION
        WHEN duplicate_object THEN NULL;
    END $$;
    """)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Asia/Tashkent"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_id"),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    op.create_table(
        "habits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=140), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "habit_reminder_times",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("habit_id", sa.Integer(), nullable=False),
        sa.Column("time_local", sa.Time(timezone=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["habit_id"], ["habits.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("habit_id", "time_local", name="uq_habit_time"),
    )

    op.create_table(
        "habit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("habit_id", sa.Integer(), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("status", habit_status, nullable=False, server_default="not_done"),
        sa.Column("done_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["habit_id"], ["habits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "habit_id", "local_date", name="uq_user_habit_date"),
    )
    op.create_index("ix_habit_logs_local_date", "habit_logs", ["local_date"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_habit_logs_local_date", table_name="habit_logs")
    op.drop_table("habit_logs")
    op.drop_table("habit_reminder_times")
    op.drop_table("habits")
    op.drop_index("ix_users_telegram_id", table_name="users")
    op.drop_table("users")

    # ✅ Drop ENUM type safely
    op.execute("DROP TYPE IF EXISTS habit_status;")