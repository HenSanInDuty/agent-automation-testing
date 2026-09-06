from infrastructure.persistence.models import Base


def test_control_plane_schema_contains_tenant_scoped_aggregates() -> None:
    expected_tables = {
        "configs",
        "projects",
        "test_cases",
        "test_runs",
        "artifacts",
        "agent_proposals",
        "run_reports",
        "approvals",
        "audit_events",
        "outbox_events",
        "users",
        "tenant_memberships",
        "sessions",
        "visual_exploration_sessions",
        "visual_action_proposals",
        "visual_replay_frames",
    }

    assert expected_tables <= set(Base.metadata.tables)
    for table_name in expected_tables - {"users", "sessions"}:
        assert "tenant_id" in Base.metadata.tables[table_name].c


def test_visual_replay_schema_preserves_private_metadata_and_action_source() -> None:
    frame = Base.metadata.tables["visual_replay_frames"]
    actions = Base.metadata.tables["visual_action_proposals"]

    assert {"session_id", "state_id", "storage_key", "checksum", "size", "deleted_at"} <= set(
        frame.c.keys()
    )
    assert "retention_until" not in frame.c
    assert actions.c.originating_state_id.nullable
    assert any(
        constraint.name == "uq_visual_replay_frame_state" for constraint in frame.constraints
    )
