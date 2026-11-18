"""Allow up to twenty explicitly configured Vision model calls."""

from alembic import op

revision = "a4c6e8f01234"
down_revision = "f3a4b5c6d7e9"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_codex_job_sequence", "codex_bridge_jobs", type_="check")
    op.create_check_constraint("ck_codex_job_sequence", "codex_bridge_jobs",
                               "request_sequence BETWEEN 1 AND 20 AND fencing_token > 0")


def downgrade():
    # Shrinking this bound can invalidate retained requests 11..20.
    raise RuntimeError("Retain model-call history; disable new writers before rollback")
