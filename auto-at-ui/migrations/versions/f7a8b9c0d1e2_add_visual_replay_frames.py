"""add persistent visual replay frame metadata

Revision ID: f7a8b9c0d1e2
Revises: f6a7b8c9d0e1
Create Date: 2026-09-06 18:55:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "f7a8b9c0d1e2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "visual_action_proposals",
        sa.Column("originating_state_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_visual_action_proposals_originating_state",
        "visual_action_proposals",
        "visual_exploration_states",
        ["originating_state_id"],
        ["id"],
    )
    op.create_index(
        "ix_visual_action_proposals_originating_state",
        "visual_action_proposals",
        ["originating_state_id"],
    )
    op.create_table(
        "visual_replay_frames",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=200), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("state_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["visual_exploration_sessions.id"]),
        sa.ForeignKeyConstraint(["state_id"], ["visual_exploration_states.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "state_id", name="uq_visual_replay_frame_state"),
    )
    op.create_index("ix_visual_replay_frames_session_id", "visual_replay_frames", ["session_id"])
    op.create_index("ix_visual_replay_frames_state_id", "visual_replay_frames", ["state_id"])
    op.create_index(
        "ix_visual_replay_frames_tenant_session_sequence",
        "visual_replay_frames",
        ["tenant_id", "session_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_visual_replay_frames_tenant_session_sequence", table_name="visual_replay_frames"
    )
    op.drop_index("ix_visual_replay_frames_state_id", table_name="visual_replay_frames")
    op.drop_index("ix_visual_replay_frames_session_id", table_name="visual_replay_frames")
    op.drop_table("visual_replay_frames")
    op.drop_index(
        "ix_visual_action_proposals_originating_state", table_name="visual_action_proposals"
    )
    op.drop_constraint(
        "fk_visual_action_proposals_originating_state",
        "visual_action_proposals",
        type_="foreignkey",
    )
    op.drop_column("visual_action_proposals", "originating_state_id")
