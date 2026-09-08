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
        "visual_trajectory_edges",
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


def test_trajectory_edges_link_immutable_redacted_outcomes() -> None:
    edges = Base.metadata.tables["visual_trajectory_edges"]

    assert {
        "tenant_id", "session_id", "parent_state_id", "proposal_id", "child_state_id",
        "attempt", "action", "confidence", "status", "outcome_code", "duration_ms",
        "url_fingerprint", "child_screenshot_checksum",
    } <= set(edges.c.keys())
    assert "target_url" not in edges.c
    assert any(
        constraint.name == "uq_visual_trajectory_attempt" for constraint in edges.constraints
    )


def test_operation_evidence_is_separate_scoped_and_generation_link_is_nullable():
    for name in ("visual_operations", "visual_operation_frames", "visual_locator_evidence",
                 "visual_locator_handoffs"):
        table = Base.metadata.tables[name]
        assert {"tenant_id", "project_id", "session_id"} <= set(table.c.keys())
        assert any(len(fk.column_keys) >= 3 for fk in table.foreign_key_constraints)
    assert Base.metadata.tables["generation_requests"].c.vision_handoff_id.nullable
    assert "checkpoint" in Base.metadata.tables["visual_exploration_states"].c
    frames = Base.metadata.tables["visual_operation_frames"]
    assert {"storage_key", "deleted_at", "operation_id", "role"} <= set(frames.c.keys())
    assert "retention_until" not in frames.c
