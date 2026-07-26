from infrastructure.persistence.models import Base


def test_control_plane_schema_contains_tenant_scoped_aggregates() -> None:
    expected_tables = {
        "configs",
        "projects",
        "test_cases",
        "test_runs",
        "artifacts",
        "agent_proposals",
        "approvals",
        "audit_events",
        "outbox_events",
    }

    assert expected_tables <= set(Base.metadata.tables)
    for table_name in expected_tables:
        assert "tenant_id" in Base.metadata.tables[table_name].c
