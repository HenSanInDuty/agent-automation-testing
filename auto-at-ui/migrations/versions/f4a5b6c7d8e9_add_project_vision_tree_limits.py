"""add project vision tree limits

Revision ID: f4a5b6c7d8e9
Revises: b5c6d7e8f9a0
"""

import sqlalchemy as sa
from alembic import op

revision = "f4a5b6c7d8e9"
down_revision = "b5c6d7e8f9a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_execution_policies",
        sa.Column("vision_max_hops", sa.Integer(), nullable=False, server_default="5"),
    )
    op.add_column(
        "project_execution_policies",
        sa.Column("vision_max_states", sa.Integer(), nullable=False, server_default="50"),
    )
    op.alter_column("project_execution_policies", "vision_max_hops", server_default=None)
    op.alter_column("project_execution_policies", "vision_max_states", server_default=None)
    op.add_column(
        "visual_exploration_sessions",
        sa.Column("max_hops", sa.Integer(), nullable=False, server_default="5"),
    )
    op.add_column(
        "visual_exploration_sessions",
        sa.Column("max_states", sa.Integer(), nullable=False, server_default="50"),
    )
    op.alter_column("visual_exploration_sessions", "max_hops", server_default=None)
    op.alter_column("visual_exploration_sessions", "max_states", server_default=None)
    op.create_table(
        "visual_exploration_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=200), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("hop", sa.Integer(), nullable=False),
        sa.Column("screenshot_checksum", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["visual_exploration_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "id"),
    )
    op.create_index(
        "ix_visual_exploration_states_session_id", "visual_exploration_states", ["session_id"]
    )
    op.create_index(
        "ix_visual_exploration_states_parent_id", "visual_exploration_states", ["parent_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_visual_exploration_states_parent_id", table_name="visual_exploration_states")
    op.drop_index("ix_visual_exploration_states_session_id", table_name="visual_exploration_states")
    op.drop_table("visual_exploration_states")
    op.drop_column("visual_exploration_sessions", "max_states")
    op.drop_column("visual_exploration_sessions", "max_hops")
    op.drop_column("project_execution_policies", "vision_max_states")
    op.drop_column("project_execution_policies", "vision_max_hops")
