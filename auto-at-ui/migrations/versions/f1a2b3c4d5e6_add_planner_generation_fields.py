"""add generated planner state and review title

Revision ID: f1a2b3c4d5e6
Revises: e5a8d9f2c1b4
"""

import sqlalchemy as sa
from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "e5a8d9f2c1b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("generation_requests", sa.Column("failure_reason", sa.Text(), nullable=True))
    op.add_column(
        "generated_test_drafts",
        sa.Column("title", sa.String(200), nullable=False, server_default="Generated test"),
    )
    op.alter_column("generated_test_drafts", "title", server_default=None)


def downgrade() -> None:
    op.drop_column("generated_test_drafts", "title")
    op.drop_column("generation_requests", "failure_reason")
