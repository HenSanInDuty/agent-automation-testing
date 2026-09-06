"""scope activity progress to visual exploration sessions

Revision ID: f6a7b8c9d0e1
Revises: f5a6b7c8d9e0
Create Date: 2026-09-06 15:29:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "f6a7b8c9d0e1"
down_revision = "f5a6b7c8d9e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "activity_events",
        sa.Column("visual_exploration_session_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "activity_events", sa.Column("progress_key", sa.String(length=200), nullable=True)
    )
    op.create_foreign_key(
        "fk_activity_events_vision_session",
        "activity_events",
        "visual_exploration_sessions",
        ["visual_exploration_session_id"],
        ["id"],
    )
    op.create_index(
        "ix_activity_events_vision_session_timeline",
        "activity_events",
        ["tenant_id", "visual_exploration_session_id", "occurred_at"],
    )
    op.create_unique_constraint(
        "uq_activity_vision_progress",
        "activity_events",
        ["visual_exploration_session_id", "progress_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_activity_vision_progress", "activity_events", type_="unique")
    op.drop_index("ix_activity_events_vision_session_timeline", table_name="activity_events")
    op.drop_constraint("fk_activity_events_vision_session", "activity_events", type_="foreignkey")
    op.drop_column("activity_events", "progress_key")
    op.drop_column("activity_events", "visual_exploration_session_id")
