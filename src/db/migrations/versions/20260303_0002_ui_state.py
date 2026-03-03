"""add ui_state table for app-like navigation

Revision ID: 20260303_0002
Revises: 20260303_0001
Create Date: 2026-03-03 12:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260303_0002"
down_revision = "20260303_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ui_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("screen_message_id", sa.BigInteger(), nullable=True),
        sa.Column("current_screen", sa.String(length=64), nullable=False, server_default="HOME"),
        sa.Column(
            "stack",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_ui_state_user_id", "ui_state", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_ui_state_user_id", table_name="ui_state")
    op.drop_table("ui_state")
