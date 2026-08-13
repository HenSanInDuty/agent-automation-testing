"""add immutable tenant-scoped run reports

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "c5d6e7f8a9b0"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "run_reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.String(200), nullable=False, index=True),
        sa.Column(
            "run_id",
            sa.Uuid(),
            sa.ForeignKey("test_runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("correlation_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("report_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("schema_version", sa.String(20), nullable=False),
        sa.Column("prompt_version", sa.String(100), nullable=False),
        sa.Column("deterministic_status", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, index=True),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column("provenance", JSONB, nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "run_id", "report_version"),
    )
    op.alter_column("run_reports", "report_version", server_default=None)


def downgrade() -> None:
    op.drop_table("run_reports")
