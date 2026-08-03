"""cascade activity records when a test run is deleted

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
"""

from alembic import op

revision = "b4c5d6e7f8a9"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("activity_events_run_id_fkey", "activity_events", type_="foreignkey")
    op.create_foreign_key(
        "activity_events_run_id_fkey",
        "activity_events",
        "test_runs",
        ["run_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("activity_events_run_id_fkey", "activity_events", type_="foreignkey")
    op.create_foreign_key(
        "activity_events_run_id_fkey", "activity_events", "test_runs", ["run_id"], ["id"]
    )
