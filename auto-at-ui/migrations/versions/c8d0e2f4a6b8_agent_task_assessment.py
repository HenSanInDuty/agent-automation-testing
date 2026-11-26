"""Add the agent task assessment and the owned-test-target project flag (ADR-046).

Revision ID: c8d0e2f4a6b8
Revises: b7c9d1e3f5a7

Additive only. `task_assessment` is nullable, so every existing session keeps its meaning.
`vision_owned_test_target` defaults to false (constant default: metadata-only ADD COLUMN on
PostgreSQL 11+), so every existing project keeps the read-only agent rules. Downgrade drops
both columns; assessments of finished agent-loop sessions are lost and every project returns
to the read-only rules.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c8d0e2f4a6b8"
down_revision = "b7c9d1e3f5a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "visual_exploration_sessions",
        sa.Column("task_assessment", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "project_execution_policies",
        sa.Column(
            "vision_owned_test_target", sa.Boolean(), server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("project_execution_policies", "vision_owned_test_target")
    op.drop_column("visual_exploration_sessions", "task_assessment")
