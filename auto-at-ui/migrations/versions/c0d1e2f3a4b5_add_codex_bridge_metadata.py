"""Add local Codex consent snapshots, target bindings and scoped job metadata."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "c0d1e2f3a4b5"
down_revision = "f9a0b1c2d3e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("visual_exploration_sessions", sa.Column("model_input_policy", JSONB))
    op.add_column("visual_action_proposals", sa.Column("target_binding", JSONB))
    op.create_table(
        "codex_bridge_jobs",
        sa.Column("job_id", sa.Uuid(), primary_key=True),
        sa.Column("bridge_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(200), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("fencing_token", sa.Integer(), nullable=False),
        sa.Column("request_sequence", sa.Integer(), nullable=False),
        sa.Column("observation_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("state_fingerprint", sa.String(64), nullable=False),
        sa.Column("stage", sa.String(10), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("response_hash", sa.String(64)),
        sa.Column("safe_reason", sa.String(64)),
        sa.Column("usage", JSONB),
        sa.Column("cli_version", sa.String(32)),
        sa.Column("actual_model", sa.String(200)),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id", "session_id"],
            ["visual_exploration_sessions.tenant_id", "visual_exploration_sessions.project_id",
             "visual_exploration_sessions.id"], name="fk_codex_job_session",
        ),
        sa.UniqueConstraint("session_id", "request_sequence", name="uq_codex_job_sequence"),
        sa.CheckConstraint("request_sequence BETWEEN 1 AND 10 AND fencing_token > 0",
                           name="ck_codex_job_sequence"),
        sa.CheckConstraint("stage IN ('dom', 'image')", name="ck_codex_job_stage"),
        sa.CheckConstraint(
            "status IN ('queued', 'claimed', 'running', 'completed',"
            " 'failed', 'cancelled', 'expired')",
            name="ck_codex_job_status",
        ),
        sa.CheckConstraint("deadline > created_at AND updated_at >= created_at",
                           name="ck_codex_job_times"),
    )
    for column in ("tenant_id", "bridge_id", "correlation_id", "deadline"):
        op.create_index(f"ix_codex_bridge_jobs_{column}", "codex_bridge_jobs", [column])
    op.create_index("ix_codex_job_scope", "codex_bridge_jobs",
                    ["tenant_id", "project_id", "session_id"])
    # Protect immutable snapshots and metadata even from accidental bulk SQL updates.
    op.execute("""
        CREATE FUNCTION guard_codex_metadata() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_TABLE_NAME = 'visual_exploration_sessions' THEN
            IF NEW.model_input_policy IS DISTINCT FROM OLD.model_input_policy THEN
              RAISE EXCEPTION 'model input policy is immutable';
            END IF;
          ELSIF TG_TABLE_NAME = 'visual_action_proposals' THEN
            IF NEW.target_binding IS DISTINCT FROM OLD.target_binding THEN
              RAISE EXCEPTION 'proposal target binding is immutable';
            END IF;
          ELSE
            IF (to_jsonb(NEW) - ARRAY['status','updated_at','response_hash','safe_reason',
                                     'usage','cli_version','actual_model']) IS DISTINCT FROM
               (to_jsonb(OLD) - ARRAY['status','updated_at','response_hash','safe_reason',
                                     'usage','cli_version','actual_model']) THEN
              RAISE EXCEPTION 'bridge job identity is immutable';
            END IF;
            IF NEW IS DISTINCT FROM OLD AND NOT (
              (OLD.status = 'queued'
                AND NEW.status IN ('claimed','failed','cancelled','expired')) OR
              (OLD.status = 'claimed'
                AND NEW.status IN ('running','failed','cancelled','expired')) OR
              (OLD.status = 'running'
                AND NEW.status IN ('completed','failed','cancelled','expired'))
            ) THEN
              RAISE EXCEPTION 'invalid or terminal bridge job transition';
            END IF;
            IF NEW.updated_at < OLD.updated_at THEN
              RAISE EXCEPTION 'bridge job time cannot go backwards';
            END IF;
          END IF;
          RETURN NEW;
        END $$;
    """)
    for table in ("visual_exploration_sessions", "visual_action_proposals", "codex_bridge_jobs"):
        op.execute(f"""CREATE TRIGGER guard_codex_metadata BEFORE UPDATE ON {table}
                       FOR EACH ROW EXECUTE FUNCTION guard_codex_metadata()""")


def downgrade() -> None:
    raise RuntimeError("Retain Codex audit metadata; disable and drain writers before rollback")
