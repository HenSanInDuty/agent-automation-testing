"""store encrypted visual request intent for bounded retry

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-08-31 18:33:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "b5c6d7e8f9a0"
down_revision = "a4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "visual_exploration_sessions",
        sa.Column("encrypted_task_intent", sa.Text(), nullable=True),
    )
    op.add_column(
        "visual_exploration_sessions",
        sa.Column("intent_retention_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE visual_exploration_sessions "
        "SET encrypted_task_intent = '', intent_retention_until = created_at "
        "WHERE encrypted_task_intent IS NULL"
    )
    op.alter_column("visual_exploration_sessions", "encrypted_task_intent", nullable=False)
    op.alter_column("visual_exploration_sessions", "intent_retention_until", nullable=False)
    op.create_index(
        "ix_visual_exploration_sessions_intent_retention_until",
        "visual_exploration_sessions",
        ["intent_retention_until"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_visual_exploration_sessions_intent_retention_until",
        "visual_exploration_sessions",
    )
    op.drop_column("visual_exploration_sessions", "intent_retention_until")
    op.drop_column("visual_exploration_sessions", "encrypted_task_intent")
