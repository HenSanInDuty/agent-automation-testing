"""add append-only activity timeline

Revision ID: f2a3b4c5d6e7
Revises: e5a8d9f2c1b4
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "f2a3b4c5d6e7"
down_revision = "e5a8d9f2c1b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "activity_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.String(200), nullable=False),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("test_runs.id")),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("stage", sa.String(100), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("safe_summary", sa.Text(), nullable=False),
        sa.Column("metadata", JSONB, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_activity_events_run_timeline",
        "activity_events",
        ["tenant_id", "run_id", "occurred_at"],
    )
    op.create_index(
        "ix_activity_events_correlation_timeline",
        "activity_events",
        ["tenant_id", "correlation_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_activity_events_correlation_timeline", table_name="activity_events")
    op.drop_index("ix_activity_events_run_timeline", table_name="activity_events")
    op.drop_table("activity_events")
