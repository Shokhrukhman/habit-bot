"""enforce single reminder time per habit

Revision ID: 20260303_0004
Revises: 20260303_0003
Create Date: 2026-03-03 14:10:00
"""

from __future__ import annotations

from alembic import op


revision = "20260303_0004"
down_revision = "20260303_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep exactly one time per habit: earliest by time_local, then created_at/id.
    op.execute(
        """
        DELETE FROM habit_reminder_times hrt
        USING (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY habit_id
                    ORDER BY time_local ASC, created_at ASC, id ASC
                ) AS rn
            FROM habit_reminder_times
        ) ranked
        WHERE hrt.id = ranked.id
          AND ranked.rn > 1;
        """
    )
    op.execute(
        "ALTER TABLE habit_reminder_times DROP CONSTRAINT IF EXISTS uq_habit_time;"
    )
    op.execute(
        "ALTER TABLE habit_reminder_times ADD CONSTRAINT uq_habit_time UNIQUE (habit_id);"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE habit_reminder_times DROP CONSTRAINT IF EXISTS uq_habit_time;"
    )
    op.execute(
        "ALTER TABLE habit_reminder_times ADD CONSTRAINT uq_habit_time UNIQUE (habit_id, time_local);"
    )
