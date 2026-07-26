"""add proposal and approval audit timestamps

Revision ID: d4f7c8a9b2e3
Revises: c3a9a6b2e1f4
"""

import sqlalchemy as sa
from alembic import op

revision = "d4f7c8a9b2e3"
down_revision = "c3a9a6b2e1f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_proposals", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("approvals", sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("approvals", "decided_at")
    op.drop_column("agent_proposals", "created_at")
