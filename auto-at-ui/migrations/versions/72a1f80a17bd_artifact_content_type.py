"""persist artifact content type

Revision ID: 72a1f80a17bd
Revises: 16666d5ab085
"""

import sqlalchemy as sa
from alembic import op

revision = "72a1f80a17bd"
down_revision = "16666d5ab085"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("artifacts", sa.Column("content_type", sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column("artifacts", "content_type")
