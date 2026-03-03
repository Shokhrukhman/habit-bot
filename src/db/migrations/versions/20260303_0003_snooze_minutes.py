"""add user snooze minutes setting

Revision ID: 20260303_0003
Revises: 20260303_0002
Create Date: 2026-03-03 13:05:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260303_0003"
down_revision = "20260303_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("snooze_minutes", sa.Integer(), nullable=False, server_default="10"),
    )


def downgrade() -> None:
    op.drop_column("users", "snooze_minutes")
