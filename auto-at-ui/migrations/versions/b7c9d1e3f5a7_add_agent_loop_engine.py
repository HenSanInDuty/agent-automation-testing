"""Add the agent-loop exploration engine selector and its per-step log.

Revision ID: b7c9d1e3f5a7
Revises: a4c6e8f01234

Additive only. `exploration_engine` defaults to 'planner' (constant default: metadata-only
ADD COLUMN on PostgreSQL 11+), so every existing session keeps the v4 planner behaviour.
Does not touch `ck_codex_job_sequence`. Downgrade drops the new table and column; sessions
created with engine 'agent_loop' lose that marker and their step log, so disable the
writers (VISION_AGENT_LOOP_ENABLED=false) before rolling back.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b7c9d1e3f5a7"
down_revision = "a4c6e8f01234"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "visual_exploration_sessions",
        sa.Column(
            "exploration_engine", sa.String(length=20), server_default="planner", nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_visual_session_exploration_engine", "visual_exploration_sessions",
        "exploration_engine IN ('planner', 'agent_loop')",
    )
    op.create_table(
        "visual_agent_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("snapshot_version", sa.Integer(), nullable=False),
        sa.Column("evaluation_previous_goal", sa.Text(), nullable=False),
        sa.Column("memory", sa.Text(), nullable=False),
        sa.Column("next_goal", sa.Text(), nullable=False),
        sa.Column("actions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("operation_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("stop_reason", sa.String(length=80), nullable=True),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id", "session_id"],
            [
                "visual_exploration_sessions.tenant_id",
                "visual_exploration_sessions.project_id",
                "visual_exploration_sessions.id",
            ],
            name="fk_visual_agent_step_session",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "step_index", name="uq_visual_agent_step_index"),
    )
    op.create_index(
        op.f("ix_visual_agent_steps_tenant_id"), "visual_agent_steps", ["tenant_id"], unique=False,
    )


def downgrade() -> None:
    op.drop_table("visual_agent_steps")
    op.drop_constraint(
        "ck_visual_session_exploration_engine", "visual_exploration_sessions", type_="check",
    )
    op.drop_column("visual_exploration_sessions", "exploration_engine")
