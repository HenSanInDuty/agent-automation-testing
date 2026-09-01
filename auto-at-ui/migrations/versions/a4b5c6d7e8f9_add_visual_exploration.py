"""Add safe metadata tables for governed visual exploration.

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-08-31
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a4b5c6d7e8f9"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "visual_exploration_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=200), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_url", sa.Text(), nullable=False),
        sa.Column("intent_hash", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("policy_version", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("max_steps", sa.Integer(), nullable=False),
        sa.Column("max_screenshot_bytes", sa.Integer(), nullable=False),
        sa.Column("max_session_seconds", sa.Integer(), nullable=False),
        sa.Column("max_cost_usd", sa.String(length=32), nullable=False),
        sa.Column("max_requests_per_minute", sa.Integer(), nullable=False),
        sa.Column("safe_failure_reason", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key"),
    )
    op.create_index(
        "ix_visual_exploration_sessions_tenant_id",
        "visual_exploration_sessions",
        ["tenant_id"],
    )
    op.create_index(
        "ix_visual_exploration_sessions_project_id",
        "visual_exploration_sessions",
        ["project_id"],
    )
    op.create_index(
        "ix_visual_exploration_sessions_correlation_id",
        "visual_exploration_sessions",
        ["correlation_id"],
    )
    op.create_index(
        "ix_visual_exploration_sessions_state",
        "visual_exploration_sessions",
        ["state"],
    )
    op.create_index(
        "ix_visual_exploration_sessions_created_at",
        "visual_exploration_sessions",
        ["created_at"],
    )
    op.create_table(
        "visual_action_proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=200), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("action", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_checksum", sa.String(length=64), nullable=True),
        sa.Column("policy_version", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["visual_exploration_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "sequence"),
    )
    op.create_index(
        "ix_visual_action_proposals_tenant_id", "visual_action_proposals", ["tenant_id"]
    )
    op.create_index(
        "ix_visual_action_proposals_session_id", "visual_action_proposals", ["session_id"]
    )
    op.create_index(
        "ix_visual_action_proposals_correlation_id",
        "visual_action_proposals",
        ["correlation_id"],
    )


def downgrade() -> None:
    op.drop_table("visual_action_proposals")
    op.drop_table("visual_exploration_sessions")
