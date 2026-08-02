"""add test run creation timestamp

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
"""

import sqlalchemy as sa
from alembic import op

revision = "b3c4d5e6f7a8"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "test_runs",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_test_runs_created_at", "test_runs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_test_runs_created_at", table_name="test_runs")
    op.drop_column("test_runs", "created_at")
