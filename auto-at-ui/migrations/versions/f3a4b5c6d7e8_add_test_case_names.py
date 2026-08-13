"""add mutable display names for test cases

Revision ID: f3a4b5c6d7e8
Revises: c5d6e7f8a9b0
"""

import sqlalchemy as sa
from alembic import op

revision = "f3a4b5c6d7e8"
down_revision = "c5d6e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("test_cases", sa.Column("name", sa.String(200), nullable=True))
    op.execute("UPDATE test_cases SET name = id WHERE name IS NULL")
    op.alter_column("test_cases", "name", nullable=False)


def downgrade() -> None:
    op.drop_column("test_cases", "name")
