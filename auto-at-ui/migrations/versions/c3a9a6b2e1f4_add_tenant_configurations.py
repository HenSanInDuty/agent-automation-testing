"""add tenant-scoped non-secret configurations

Revision ID: c3a9a6b2e1f4
Revises: 72a1f80a17bd
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c3a9a6b2e1f4"
down_revision = "72a1f80a17bd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "configs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tenant_id", sa.String(length=200), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "key"),
    )
    op.create_index(op.f("ix_configs_tenant_id"), "configs", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_configs_tenant_id"), table_name="configs")
    op.drop_table("configs")
