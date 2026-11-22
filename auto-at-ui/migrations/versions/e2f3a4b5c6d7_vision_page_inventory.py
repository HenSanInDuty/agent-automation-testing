"""Retain bounded page inventories alongside exploration checkpoints."""

import sqlalchemy as sa
from alembic import op

revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "visual_exploration_states", sa.Column("page_inventory", sa.JSON(), nullable=True),
    )


def downgrade():
    raise RuntimeError("Retain page coverage history; disable writers before rollback")
