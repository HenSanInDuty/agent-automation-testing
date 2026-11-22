"""Snapshot per-step timeouts without changing historical session limits."""

import sqlalchemy as sa
from alembic import op

revision = "f3a4b5c6d7e9"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("visual_exploration_sessions",
                  sa.Column("step_timeout_seconds", sa.Integer(), nullable=True))


def downgrade():
    raise RuntimeError("Retain timeout history; disable new writers before rollback")
