"""add immutable visual trajectory edges

Revision ID: f8a9b0c1d2e3
Revises: f7a8b9c0d1e2
Create Date: 2026-09-07 21:30:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "f8a9b0c1d2e3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "visual_trajectory_edges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=200), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("parent_state_id", sa.Uuid(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column("child_state_id", sa.Uuid(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("action", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("outcome_code", sa.String(length=64), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("url_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("url_change", sa.String(length=32), nullable=False, server_default="unavailable"),
        sa.Column("child_screenshot_checksum", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["visual_exploration_sessions.id"]),
        sa.ForeignKeyConstraint(["parent_state_id"], ["visual_exploration_states.id"]),
        sa.ForeignKeyConstraint(["proposal_id"], ["visual_action_proposals.id"]),
        sa.ForeignKeyConstraint(["child_state_id"], ["visual_exploration_states.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id", "proposal_id", "attempt", name="uq_visual_trajectory_attempt"
        ),
    )
    op.create_index(
        "ix_visual_trajectory_edges_tenant_id", "visual_trajectory_edges", ["tenant_id"]
    )
    op.create_index(
        "ix_visual_trajectory_edges_session_id", "visual_trajectory_edges", ["session_id"]
    )
    op.create_index(
        "ix_visual_trajectory_edges_parent_state_id",
        "visual_trajectory_edges",
        ["parent_state_id"],
    )
    op.create_index(
        "ix_visual_trajectory_edges_proposal_id", "visual_trajectory_edges", ["proposal_id"]
    )
    op.create_index(
        "ix_visual_trajectory_edges_child_state_id",
        "visual_trajectory_edges",
        ["child_state_id"],
    )
    op.create_index(
        "ix_visual_trajectory_edges_tenant_session",
        "visual_trajectory_edges",
        ["tenant_id", "session_id"],
    )


def downgrade() -> None:
    for name in (
        "ix_visual_trajectory_edges_tenant_session", "ix_visual_trajectory_edges_child_state_id",
        "ix_visual_trajectory_edges_proposal_id", "ix_visual_trajectory_edges_parent_state_id",
        "ix_visual_trajectory_edges_session_id", "ix_visual_trajectory_edges_tenant_id",
    ):
        op.drop_index(name, table_name="visual_trajectory_edges")
    op.drop_table("visual_trajectory_edges")
