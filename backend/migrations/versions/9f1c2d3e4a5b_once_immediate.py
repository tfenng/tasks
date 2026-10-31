"""once immediate

Revision ID: 9f1c2d3e4a5b
Revises: 378fd62931c0
Create Date: 2026-10-31
"""

# ruff: noqa: E501
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "9f1c2d3e4a5b"
down_revision: str | None = "378fd62931c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("trigger_config", "schedules", type_="check")
    op.create_check_constraint(
        "trigger_config",
        "schedules",
        "trigger_type = 'once' OR ("
        "trigger_type = 'cron' AND cron_expr IS NOT NULL"
        ") OR ("
        "trigger_type = 'interval' AND interval_seconds IS NOT NULL"
        ")",
    )


def downgrade() -> None:
    op.drop_constraint("trigger_config", "schedules", type_="check")
    op.create_check_constraint(
        "trigger_config",
        "schedules",
        "(trigger_type = 'once' AND fire_at IS NOT NULL) OR ("
        "trigger_type = 'cron' AND cron_expr IS NOT NULL"
        ") OR ("
        "trigger_type = 'interval' AND interval_seconds IS NOT NULL"
        ")",
    )
