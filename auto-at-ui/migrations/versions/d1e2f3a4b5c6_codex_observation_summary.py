"""Record safe observation hash/count without retaining the DOM body."""

import sqlalchemy as sa
from alembic import op

revision = "d1e2f3a4b5c6"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("codex_bridge_jobs", sa.Column("dom_sha256", sa.String(64), nullable=True))
    op.add_column("codex_bridge_jobs", sa.Column("dom_element_count", sa.Integer(), nullable=True))
    op.create_check_constraint("ck_codex_dom_count", "codex_bridge_jobs",
                               "dom_element_count IS NULL OR dom_element_count BETWEEN 0 AND 100")


def downgrade():
    raise RuntimeError("Retain Codex observation audit metadata; disable and drain writers")
