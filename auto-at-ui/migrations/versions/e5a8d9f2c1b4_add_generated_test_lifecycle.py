"""add governed generated-test lifecycle

Revision ID: e5a8d9f2c1b4
Revises: d4f7c8a9b2e3
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "e5a8d9f2c1b4"
down_revision = "d4f7c8a9b2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_execution_policies",
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id"), primary_key=True),
        sa.Column("tenant_id", sa.String(200), nullable=False, index=True),
        sa.Column("allowed_origins", JSONB, nullable=False),
    )
    op.create_table(
        "generation_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.String(200), nullable=False, index=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("target_url", sa.Text(), nullable=False),
        sa.Column("redacted_request", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.UniqueConstraint("tenant_id", "idempotency_key"),
    )
    op.create_table(
        "generated_test_drafts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.String(200), nullable=False, index=True),
        sa.Column(
            "planning_request_id",
            sa.Uuid(),
            sa.ForeignKey("generation_requests.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("playwright_test_source", sa.Text(), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("assumptions", JSONB, nullable=False),
        sa.Column("stop_conditions", JSONB, nullable=False),
        sa.Column("provenance", JSONB, nullable=False),
        sa.Column("linked_test_case_id", sa.String(200)),
        sa.Column("linked_run_id", sa.Uuid()),
    )
    op.create_table(
        "generated_test_decisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.String(200), nullable=False, index=True),
        sa.Column("draft_id", sa.Uuid(), sa.ForeignKey("generated_test_drafts.id"), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("decided_by", sa.String(200), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.UniqueConstraint("draft_id"),
    )


def downgrade() -> None:
    op.drop_table("generated_test_decisions")
    op.drop_table("generated_test_drafts")
    op.drop_table("generation_requests")
    op.drop_table("project_execution_policies")
