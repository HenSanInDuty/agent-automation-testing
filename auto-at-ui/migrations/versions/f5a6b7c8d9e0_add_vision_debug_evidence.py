"""add encrypted, expiring vision debug evidence

Revision ID: f5a6b7c8d9e0
Revises: f4a5b6c7d8e9
Create Date: 2026-09-06 03:10:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "f5a6b7c8d9e0"
down_revision = "f4a5b6c7d8e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vision_debug_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=200), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("state_id", sa.Uuid(), nullable=True),
        sa.Column("attempt_key", sa.String(length=200), nullable=False),
        sa.Column("diagnostic_code", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("encrypted_payload", sa.Text(), nullable=False),
        sa.Column("key_id", sa.String(length=100), nullable=False),
        sa.Column("payload_checksum", sa.String(length=64), nullable=True),
        sa.Column("payload_byte_count", sa.Integer(), nullable=False),
        sa.Column("redaction_version", sa.String(length=100), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["visual_exploration_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id", "state_id", "attempt_key", name="uq_vision_debug_attempt"
        ),
    )
    op.create_index(
        "ix_vision_debug_evidence_tenant_session",
        "vision_debug_evidence",
        ["tenant_id", "session_id"],
    )
    op.create_index(
        "ix_vision_debug_evidence_retention",
        "vision_debug_evidence",
        ["retention_until", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_vision_debug_evidence_retention", table_name="vision_debug_evidence")
    op.drop_index("ix_vision_debug_evidence_tenant_session", table_name="vision_debug_evidence")
    op.drop_table("vision_debug_evidence")
