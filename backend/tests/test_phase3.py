"""
tests/test_phase3.py – Phase 3 API Layer test suite.

Covers all REST endpoints and the WebSocket handler introduced in Phase 3:
  - GET/POST/PUT/DELETE  /api/v1/admin/llm-profiles
  - POST                 /api/v1/admin/llm-profiles/{id}/set-default
  - POST                 /api/v1/admin/llm-profiles/{id}/test
  - GET/PUT              /api/v1/admin/agent-configs
  - POST                 /api/v1/admin/agent-configs/{agent_id}/reset
  - POST                 /api/v1/admin/agent-configs/reset-all
  - POST                 /api/v1/pipeline/run
  - GET                  /api/v1/pipeline/runs
  - GET/DELETE           /api/v1/pipeline/runs/{run_id}
  - POST                 /api/v1/pipeline/runs/{run_id}/cancel
  - GET                  /api/v1/pipeline/runs/{run_id}/results
  - WS                   /ws/pipeline/{run_id}

All tests run against an isolated in-memory SQLite database.
No real LLM calls are made; pipeline execution is mocked.
"""

from __future__ import annotations

import io
import json
import uuid
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# ── App & DB wiring ───────────────────────────────────────────────────────────
from app.api.v1.deps import get_db
from app.db.database import Base
from app.db.seed import DEFAULT_AGENT_CONFIGS, seed_all
from app.main import app

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

TEST_DB_URL = "sqlite://"  # pure in-memory, discarded after each test session


@pytest.fixture(scope="session")
def engine():
    """Create a single shared engine for the test session."""
    from app.db import models  # noqa: F401 – registers ORM classes

    eng = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)
    eng.dispose()


@pytest.fixture()
def db(engine) -> Generator[Session, None, None]:
    """
    Provide a fresh DB transaction for each test.
    All changes are rolled back after the test so tests stay isolated.
    """
    connection = engine.connect()
    transaction = connection.begin()

    TestingSessionLocal = sessionmaker(
        bind=connection,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db: Session) -> Generator[TestClient, None, None]:
    """
    FastAPI TestClient that uses the test DB session via dependency override.
    Pipeline background tasks are patched to be a no-op so tests stay fast.
    """

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    # Patch the background pipeline runner so tests don't call LLMs
    with patch(
        "app.api.v1.pipeline._run_pipeline_background",
        new_callable=lambda: lambda *a, **kw: AsyncMock(return_value=None),
    ):
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c

    app.dependency_overrides.clear()


@pytest.fixture()
def seeded_client(db: Session) -> Generator[TestClient, None, None]:
    """
    Like `client` but with the default seed data pre-loaded
    (1 LLM profile + 18 agent configs).
    """
    seed_all(db)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    with patch(
        "app.api.v1.pipeline._run_pipeline_background",
        new_callable=lambda: lambda *a, **kw: AsyncMock(return_value=None),
    ):
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c

    app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_PROFILE_PAYLOAD = {
    "name": "Test-GPT4o",
    "provider": "openai",
    "model": "gpt-4o",
    "api_key": "sk-test-1234",
    "base_url": None,
    "temperature": 0.1,
    "max_tokens": 2048,
    "is_default": False,
}

_MD_FILE = (
    "requirements.md",
    io.BytesIO(b"# Requirements\n\n- REQ-001: Login\n"),
    "text/markdown",
)


def _upload_file(content: bytes = b"# test", filename: str = "req.md"):
    return ("file", (filename, io.BytesIO(content), "text/markdown"))


# ─────────────────────────────────────────────────────────────────────────────
# 1. Health check (sanity)
# ─────────────────────────────────────────────────────────────────────────────


class TestHealth:
    def test_health_ok(self, client: TestClient):
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] in ("ok", "degraded")
        assert "version" in body
        assert "database" in body


# ─────────────────────────────────────────────────────────────────────────────
# 2. LLM Profiles CRUD
# ─────────────────────────────────────────────────────────────────────────────


class TestLLMProfilesCreate:
    def test_create_profile_returns_201(self, client: TestClient):
        r = client.post("/api/v1/admin/llm-profiles", json=_PROFILE_PAYLOAD)
        assert r.status_code == 201
        body = r.json()
        assert body["id"] >= 1
        assert body["name"] == _PROFILE_PAYLOAD["name"]
        assert body["provider"] == _PROFILE_PAYLOAD["provider"]
        assert body["model"] == _PROFILE_PAYLOAD["model"]

    def test_api_key_is_masked_in_response(self, client: TestClient):
        r = client.post("/api/v1/admin/llm-profiles", json=_PROFILE_PAYLOAD)
        assert r.status_code == 201
        # The raw key must never appear in the response
        assert "sk-test-1234" not in r.text
        body = r.json()
        # Masked value should end with last 4 chars of the key
        assert body["api_key"] is not None
        assert body["api_key"].endswith("1234")
        assert "••••" in body["api_key"]

    def test_create_duplicate_name_returns_409(self, client: TestClient):
        client.post("/api/v1/admin/llm-profiles", json=_PROFILE_PAYLOAD)
        r = client.post("/api/v1/admin/llm-profiles", json=_PROFILE_PAYLOAD)
        assert r.status_code == 409

    def test_create_invalid_provider_returns_422(self, client: TestClient):
        payload = {**_PROFILE_PAYLOAD, "provider": "not_a_real_provider"}
        r = client.post("/api/v1/admin/llm-profiles", json=payload)
        assert r.status_code == 422

    def test_create_empty_name_returns_422(self, client: TestClient):
        payload = {**_PROFILE_PAYLOAD, "name": ""}
        r = client.post("/api/v1/admin/llm-profiles", json=payload)
        assert r.status_code == 422

    def test_create_temperature_out_of_range_returns_422(self, client: TestClient):
        payload = {**_PROFILE_PAYLOAD, "temperature": 3.0}
        r = client.post("/api/v1/admin/llm-profiles", json=payload)
        assert r.status_code == 422

    def test_create_with_is_default_true(self, client: TestClient):
        payload = {**_PROFILE_PAYLOAD, "is_default": True}
        r = client.post("/api/v1/admin/llm-profiles", json=payload)
        assert r.status_code == 201
        assert r.json()["is_default"] is True

    def test_only_one_default_at_a_time(self, client: TestClient):
        r1 = client.post(
            "/api/v1/admin/llm-profiles",
            json={**_PROFILE_PAYLOAD, "is_default": True},
        )
        r2 = client.post(
            "/api/v1/admin/llm-profiles",
            json={**_PROFILE_PAYLOAD, "name": "Profile-2", "is_default": True},
        )
        assert r1.status_code == 201
        assert r2.status_code == 201

        # Fetch both — only the second should be default
        id1 = r1.json()["id"]
        id2 = r2.json()["id"]
        p1 = client.get(f"/api/v1/admin/llm-profiles/{id1}").json()
        p2 = client.get(f"/api/v1/admin/llm-profiles/{id2}").json()
        assert p1["is_default"] is False
        assert p2["is_default"] is True

    def test_create_ollama_without_api_key(self, client: TestClient):
        payload = {
            "name": "Local-Ollama",
            "provider": "ollama",
            "model": "llama3",
            "api_key": None,
            "base_url": "http://localhost:11434",
            "temperature": 0.0,
            "max_tokens": 4096,
            "is_default": False,
        }
        r = client.post("/api/v1/admin/llm-profiles", json=payload)
        assert r.status_code == 201
        assert r.json()["api_key"] is None


class TestLLMProfilesRead:
    def test_list_empty(self, client: TestClient):
        r = client.get("/api/v1/admin/llm-profiles")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 0
        assert body["items"] == []

    def test_list_returns_all_profiles(self, client: TestClient):
        for i in range(3):
            client.post(
                "/api/v1/admin/llm-profiles",
                json={**_PROFILE_PAYLOAD, "name": f"Profile-{i}"},
            )
        r = client.get("/api/v1/admin/llm-profiles")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 3
        assert len(body["items"]) == 3

    def test_list_pagination_skip_limit(self, client: TestClient):
        for i in range(5):
            client.post(
                "/api/v1/admin/llm-profiles",
                json={**_PROFILE_PAYLOAD, "name": f"PaginProfile-{i}"},
            )
        r = client.get("/api/v1/admin/llm-profiles?skip=2&limit=2")
        assert r.status_code == 200
        body = r.json()
        assert len(body["items"]) == 2
        assert body["total"] == 5

    def test_get_single_found(self, client: TestClient):
        created = client.post(
            "/api/v1/admin/llm-profiles", json=_PROFILE_PAYLOAD
        ).json()
        r = client.get(f"/api/v1/admin/llm-profiles/{created['id']}")
        assert r.status_code == 200
        assert r.json()["id"] == created["id"]

    def test_get_single_not_found(self, client: TestClient):
        r = client.get("/api/v1/admin/llm-profiles/99999")
        assert r.status_code == 404

    def test_list_api_keys_always_masked(self, client: TestClient):
        client.post("/api/v1/admin/llm-profiles", json=_PROFILE_PAYLOAD)
        r = client.get("/api/v1/admin/llm-profiles")
        for item in r.json()["items"]:
            if item["api_key"] is not None:
                assert "sk-test-1234" not in item["api_key"]


class TestLLMProfilesUpdate:
    def test_partial_update_name_only(self, client: TestClient):
        created = client.post(
            "/api/v1/admin/llm-profiles", json=_PROFILE_PAYLOAD
        ).json()
        r = client.put(
            f"/api/v1/admin/llm-profiles/{created['id']}",
            json={"name": "Updated-Name"},
        )
        assert r.status_code == 200
        assert r.json()["name"] == "Updated-Name"
        assert r.json()["model"] == _PROFILE_PAYLOAD["model"]  # unchanged

    def test_update_temperature(self, client: TestClient):
        created = client.post(
            "/api/v1/admin/llm-profiles", json=_PROFILE_PAYLOAD
        ).json()
        r = client.put(
            f"/api/v1/admin/llm-profiles/{created['id']}",
            json={"temperature": 0.9},
        )
        assert r.status_code == 200
        assert r.json()["temperature"] == 0.9

    def test_update_api_key_masked_in_response(self, client: TestClient):
        created = client.post(
            "/api/v1/admin/llm-profiles", json=_PROFILE_PAYLOAD
        ).json()
        r = client.put(
            f"/api/v1/admin/llm-profiles/{created['id']}",
            json={"api_key": "sk-newkey-9999"},
        )
        assert r.status_code == 200
        assert "sk-newkey-9999" not in r.text
        assert r.json()["api_key"].endswith("9999")

    def test_update_not_found(self, client: TestClient):
        r = client.put("/api/v1/admin/llm-profiles/99999", json={"name": "x"})
        assert r.status_code == 404

    def test_update_duplicate_name_returns_409(self, client: TestClient):
        p1 = client.post("/api/v1/admin/llm-profiles", json=_PROFILE_PAYLOAD).json()
        client.post(
            "/api/v1/admin/llm-profiles",
            json={**_PROFILE_PAYLOAD, "name": "Other-Profile"},
        )
        r = client.put(
            f"/api/v1/admin/llm-profiles/{p1['id']}",
            json={"name": "Other-Profile"},
        )
        assert r.status_code == 409

    def test_update_same_name_on_same_profile_is_ok(self, client: TestClient):
        created = client.post(
            "/api/v1/admin/llm-profiles", json=_PROFILE_PAYLOAD
        ).json()
        r = client.put(
            f"/api/v1/admin/llm-profiles/{created['id']}",
            json={"name": _PROFILE_PAYLOAD["name"]},
        )
        assert r.status_code == 200

    def test_set_is_default_true_clears_other_defaults(self, client: TestClient):
        p1 = client.post(
            "/api/v1/admin/llm-profiles",
            json={**_PROFILE_PAYLOAD, "is_default": True},
        ).json()
        p2 = client.post(
            "/api/v1/admin/llm-profiles",
            json={**_PROFILE_PAYLOAD, "name": "Profile-B", "is_default": False},
        ).json()

        # Make p2 the default via PUT
        r = client.put(
            f"/api/v1/admin/llm-profiles/{p2['id']}",
            json={"is_default": True},
        )
        assert r.status_code == 200

        p1_after = client.get(f"/api/v1/admin/llm-profiles/{p1['id']}").json()
        assert p1_after["is_default"] is False


class TestLLMProfilesDelete:
    def test_delete_existing(self, client: TestClient):
        created = client.post(
            "/api/v1/admin/llm-profiles", json=_PROFILE_PAYLOAD
        ).json()
        r = client.delete(f"/api/v1/admin/llm-profiles/{created['id']}")
        assert r.status_code == 204

        # Verify it's gone
        assert (
            client.get(f"/api/v1/admin/llm-profiles/{created['id']}").status_code == 404
        )

    def test_delete_not_found(self, client: TestClient):
        r = client.delete("/api/v1/admin/llm-profiles/99999")
        assert r.status_code == 404

    def test_delete_reduces_count(self, client: TestClient):
        p = client.post("/api/v1/admin/llm-profiles", json=_PROFILE_PAYLOAD).json()
        total_before = client.get("/api/v1/admin/llm-profiles").json()["total"]
        client.delete(f"/api/v1/admin/llm-profiles/{p['id']}")
        total_after = client.get("/api/v1/admin/llm-profiles").json()["total"]
        assert total_after == total_before - 1


class TestLLMProfilesSetDefault:
    def test_set_default_returns_updated_profile(self, client: TestClient):
        created = client.post(
            "/api/v1/admin/llm-profiles",
            json={**_PROFILE_PAYLOAD, "is_default": False},
        ).json()
        r = client.post(f"/api/v1/admin/llm-profiles/{created['id']}/set-default")
        assert r.status_code == 200
        assert r.json()["is_default"] is True
        assert r.json()["id"] == created["id"]

    def test_set_default_not_found(self, client: TestClient):
        r = client.post("/api/v1/admin/llm-profiles/99999/set-default")
        assert r.status_code == 404

    def test_set_default_clears_previous_default(self, client: TestClient):
        p1 = client.post(
            "/api/v1/admin/llm-profiles",
            json={**_PROFILE_PAYLOAD, "is_default": True},
        ).json()
        p2 = client.post(
            "/api/v1/admin/llm-profiles",
            json={**_PROFILE_PAYLOAD, "name": "Profile-C", "is_default": False},
        ).json()

        client.post(f"/api/v1/admin/llm-profiles/{p2['id']}/set-default")

        p1_after = client.get(f"/api/v1/admin/llm-profiles/{p1['id']}").json()
        p2_after = client.get(f"/api/v1/admin/llm-profiles/{p2['id']}").json()

        assert p1_after["is_default"] is False
        assert p2_after["is_default"] is True


class TestLLMProfilesTest:
    def test_test_profile_no_api_key(self, client: TestClient):
        payload = {**_PROFILE_PAYLOAD, "api_key": None}
        created = client.post("/api/v1/admin/llm-profiles", json=payload).json()
        r = client.post(f"/api/v1/admin/llm-profiles/{created['id']}/test")
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is False
        assert "api key" in body["message"].lower() or "key" in body["message"].lower()

    def test_test_profile_ollama_no_key_required(self, client: TestClient):
        """Ollama doesn't require an API key — skip the 'no key' shortcircuit."""
        ollama = {
            "name": "Ollama-Llama3",
            "provider": "ollama",
            "model": "llama3",
            "api_key": None,
            "base_url": "http://localhost:11434",
            "temperature": 0.0,
            "max_tokens": 4096,
            "is_default": False,
        }
        created = client.post("/api/v1/admin/llm-profiles", json=ollama).json()

        # The call will fail because there's no actual Ollama running,
        # but it should get past the 'no api key' check and attempt a call.
        with patch("app.core.llm_factory.build_llm") as mock_build:
            mock_llm = MagicMock()
            mock_llm.call.side_effect = ConnectionRefusedError("Ollama not running")
            mock_build.return_value = mock_llm

            r = client.post(f"/api/v1/admin/llm-profiles/{created['id']}/test")
        assert r.status_code == 200
        # Should have tried and failed, not short-circuited
        body = r.json()
        assert body["success"] is False
        assert "latency_ms" in body

    def test_test_profile_successful_call(self, client: TestClient):
        created = client.post(
            "/api/v1/admin/llm-profiles", json=_PROFILE_PAYLOAD
        ).json()

        with patch("app.core.llm_factory.build_llm") as mock_build:
            mock_llm = MagicMock()
            mock_llm.call.return_value = "OK"
            mock_build.return_value = mock_llm

            r = client.post(
                f"/api/v1/admin/llm-profiles/{created['id']}/test",
                json={"prompt": "Say OK", "timeout_seconds": 10},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["response_preview"] == "OK"
        assert body["latency_ms"] is not None

    def test_test_profile_not_found(self, client: TestClient):
        r = client.post("/api/v1/admin/llm-profiles/99999/test")
        assert r.status_code == 404

    def test_test_profile_llm_build_failure(self, client: TestClient):
        created = client.post(
            "/api/v1/admin/llm-profiles", json=_PROFILE_PAYLOAD
        ).json()

        with patch(
            "app.core.llm_factory.build_llm",
            side_effect=ValueError("Unsupported provider"),
        ):
            r = client.post(f"/api/v1/admin/llm-profiles/{created['id']}/test")
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is False
        assert "Unsupported provider" in body["message"]


# ─────────────────────────────────────────────────────────────────────────────
# 3. Agent Configs
# ─────────────────────────────────────────────────────────────────────────────


class TestAgentConfigsList:
    def test_list_flat_returns_all_agents(self, seeded_client: TestClient):
        r = seeded_client.get("/api/v1/admin/agent-configs")
        assert r.status_code == 200
        agents = r.json()
        # 18 agents seeded (10 testcase + 5 execution + 3 reporting)
        assert len(agents) == 18

    def test_list_grouped_shape(self, seeded_client: TestClient):
        r = seeded_client.get("/api/v1/admin/agent-configs?grouped=true")
        assert r.status_code == 200
        body = r.json()
        assert set(body.keys()) == {"ingestion", "testcase", "execution", "reporting"}
        assert len(body["testcase"]) == 10
        assert len(body["execution"]) == 5
        assert len(body["reporting"]) == 3
        assert len(body["ingestion"]) == 0  # ingestion is pure Python, no agents

    def test_list_filter_by_stage(self, seeded_client: TestClient):
        r = seeded_client.get("/api/v1/admin/agent-configs?stage=testcase")
        assert r.status_code == 200
        agents = r.json()
        assert len(agents) == 10
        assert all(a["stage"] == "testcase" for a in agents)

    def test_list_filter_execution_stage(self, seeded_client: TestClient):
        r = seeded_client.get("/api/v1/admin/agent-configs?stage=execution")
        assert r.status_code == 200
        agents = r.json()
        assert len(agents) == 5
        assert all(a["stage"] == "execution" for a in agents)

    def test_list_filter_reporting_stage(self, seeded_client: TestClient):
        r = seeded_client.get("/api/v1/admin/agent-configs?stage=reporting")
        assert r.status_code == 200
        assert len(r.json()) == 3

    def test_list_enabled_only_all_enabled_by_default(self, seeded_client: TestClient):
        r = seeded_client.get("/api/v1/admin/agent-configs?enabled_only=true")
        assert r.status_code == 200
        # All 18 default agents are enabled
        assert len(r.json()) == 18

    def test_list_enabled_only_after_disabling_one(self, seeded_client: TestClient):
        seeded_client.put(
            "/api/v1/admin/agent-configs/requirement_analyzer",
            json={"enabled": False},
        )
        r = seeded_client.get("/api/v1/admin/agent-configs?enabled_only=true")
        assert r.status_code == 200
        assert len(r.json()) == 17

    def test_list_stage_and_enabled_combined(self, seeded_client: TestClient):
        seeded_client.put(
            "/api/v1/admin/agent-configs/requirement_analyzer",
            json={"enabled": False},
        )
        r = seeded_client.get(
            "/api/v1/admin/agent-configs?stage=testcase&enabled_only=true"
        )
        assert r.status_code == 200
        assert len(r.json()) == 9  # 10 - 1 disabled

    def test_list_summary_fields_present(self, seeded_client: TestClient):
        r = seeded_client.get("/api/v1/admin/agent-configs")
        assert r.status_code == 200
        for agent in r.json():
            assert "agent_id" in agent
            assert "display_name" in agent
            assert "stage" in agent
            assert "enabled" in agent
            assert "updated_at" in agent
            # Full text fields should NOT be present in summary
            assert "role" not in agent
            assert "goal" not in agent
            assert "backstory" not in agent


class TestAgentConfigsGet:
    def test_get_single_returns_full_fields(self, seeded_client: TestClient):
        r = seeded_client.get("/api/v1/admin/agent-configs/requirement_analyzer")
        assert r.status_code == 200
        body = r.json()
        assert body["agent_id"] == "requirement_analyzer"
        assert body["stage"] == "testcase"
        assert "role" in body
        assert "goal" in body
        assert "backstory" in body
        assert "enabled" in body
        assert "max_iter" in body

    def test_get_single_not_found(self, seeded_client: TestClient):
        r = seeded_client.get("/api/v1/admin/agent-configs/nonexistent_agent")
        assert r.status_code == 404

    def test_get_each_seeded_agent(self, seeded_client: TestClient):
        agent_ids = [c["agent_id"] for c in DEFAULT_AGENT_CONFIGS]
        for agent_id in agent_ids:
            r = seeded_client.get(f"/api/v1/admin/agent-configs/{agent_id}")
            assert r.status_code == 200, f"Expected 200 for agent_id={agent_id!r}"


class TestAgentConfigsUpdate:
    def test_update_display_name(self, seeded_client: TestClient):
        r = seeded_client.put(
            "/api/v1/admin/agent-configs/requirement_analyzer",
            json={"display_name": "Custom Requirement Analyzer"},
        )
        assert r.status_code == 200
        assert r.json()["display_name"] == "Custom Requirement Analyzer"

    def test_update_role_goal_backstory(self, seeded_client: TestClient):
        r = seeded_client.put(
            "/api/v1/admin/agent-configs/rule_parser",
            json={
                "role": "Custom Role",
                "goal": "Custom Goal",
                "backstory": "Custom backstory text.",
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["role"] == "Custom Role"
        assert body["goal"] == "Custom Goal"
        assert body["backstory"] == "Custom backstory text."

    def test_update_max_iter(self, seeded_client: TestClient):
        r = seeded_client.put(
            "/api/v1/admin/agent-configs/test_case_generator",
            json={"max_iter": 10},
        )
        assert r.status_code == 200
        assert r.json()["max_iter"] == 10

    def test_update_verbose_flag(self, seeded_client: TestClient):
        r = seeded_client.put(
            "/api/v1/admin/agent-configs/scope_classifier",
            json={"verbose": True},
        )
        assert r.status_code == 200
        assert r.json()["verbose"] is True

    def test_update_enabled_flag(self, seeded_client: TestClient):
        r = seeded_client.put(
            "/api/v1/admin/agent-configs/dependency_agent",
            json={"enabled": False},
        )
        assert r.status_code == 200
        assert r.json()["enabled"] is False

    def test_update_assigns_llm_profile(self, seeded_client: TestClient):
        # Create a profile first
        profile = seeded_client.post(
            "/api/v1/admin/llm-profiles", json=_PROFILE_PAYLOAD
        ).json()
        r = seeded_client.put(
            "/api/v1/admin/agent-configs/automation_agent",
            json={"llm_profile_id": profile["id"]},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["llm_profile_id"] == profile["id"]
        assert body["llm_profile"] is not None
        assert body["llm_profile"]["id"] == profile["id"]

    def test_update_invalid_llm_profile_returns_404(self, seeded_client: TestClient):
        r = seeded_client.put(
            "/api/v1/admin/agent-configs/automation_agent",
            json={"llm_profile_id": 99999},
        )
        assert r.status_code == 404

    def test_update_not_found_agent(self, seeded_client: TestClient):
        r = seeded_client.put(
            "/api/v1/admin/agent-configs/ghost_agent",
            json={"max_iter": 3},
        )
        assert r.status_code == 404

    def test_update_max_iter_out_of_range(self, seeded_client: TestClient):
        r = seeded_client.put(
            "/api/v1/admin/agent-configs/requirement_analyzer",
            json={"max_iter": 0},
        )
        assert r.status_code == 422

    def test_update_invalid_stage_returns_422(self, seeded_client: TestClient):
        r = seeded_client.put(
            "/api/v1/admin/agent-configs/requirement_analyzer",
            json={"stage": "not_a_real_stage"},
        )
        assert r.status_code == 422

    def test_update_preserves_unset_fields(self, seeded_client: TestClient):
        # Get original
        original = seeded_client.get(
            "/api/v1/admin/agent-configs/requirement_analyzer"
        ).json()

        # Only update verbose
        seeded_client.put(
            "/api/v1/admin/agent-configs/requirement_analyzer",
            json={"verbose": True},
        )

        # Everything else should be unchanged
        updated = seeded_client.get(
            "/api/v1/admin/agent-configs/requirement_analyzer"
        ).json()
        assert updated["role"] == original["role"]
        assert updated["goal"] == original["goal"]
        assert updated["max_iter"] == original["max_iter"]
        assert updated["verbose"] is True


class TestAgentConfigsReset:
    def test_reset_single_reverts_to_defaults(self, seeded_client: TestClient):
        # Mutate an agent
        seeded_client.put(
            "/api/v1/admin/agent-configs/requirement_analyzer",
            json={
                "role": "CUSTOM ROLE",
                "goal": "CUSTOM GOAL",
                "max_iter": 99,
                "verbose": True,
            },
        )

        # Reset it
        r = seeded_client.post("/api/v1/admin/agent-configs/requirement_analyzer/reset")
        assert r.status_code == 200
        body = r.json()
        assert body["agent_id"] == "requirement_analyzer"

        config = body["config"]
        # Should match the seed default
        default = next(
            c for c in DEFAULT_AGENT_CONFIGS if c["agent_id"] == "requirement_analyzer"
        )
        assert config["role"] == default["role"]
        assert config["goal"] == default["goal"]
        assert config["max_iter"] == default["max_iter"]
        assert config["verbose"] is False  # default

    def test_reset_clears_llm_profile_override(self, seeded_client: TestClient):
        profile = seeded_client.post(
            "/api/v1/admin/llm-profiles", json=_PROFILE_PAYLOAD
        ).json()
        seeded_client.put(
            "/api/v1/admin/agent-configs/requirement_analyzer",
            json={"llm_profile_id": profile["id"]},
        )

        r = seeded_client.post("/api/v1/admin/agent-configs/requirement_analyzer/reset")
        assert r.status_code == 200
        assert r.json()["config"]["llm_profile_id"] is None

    def test_reset_not_found_agent(self, seeded_client: TestClient):
        r = seeded_client.post("/api/v1/admin/agent-configs/ghost_agent/reset")
        assert r.status_code == 404

    def test_reset_all_reverts_all_agents(self, seeded_client: TestClient):
        # Mutate several agents
        for agent_id in ["requirement_analyzer", "rule_parser", "scope_classifier"]:
            seeded_client.put(
                f"/api/v1/admin/agent-configs/{agent_id}",
                json={"role": "MUTATED", "max_iter": 99},
            )

        r = seeded_client.post("/api/v1/admin/agent-configs/reset-all")
        assert r.status_code == 200
        body = r.json()
        assert body["reset_count"] == 18
        assert "agent_ids" in body

        # Verify each mutated agent is back to defaults
        for agent_id in ["requirement_analyzer", "rule_parser", "scope_classifier"]:
            default = next(
                c for c in DEFAULT_AGENT_CONFIGS if c["agent_id"] == agent_id
            )
            agent = seeded_client.get(f"/api/v1/admin/agent-configs/{agent_id}").json()
            assert agent["role"] == default["role"]
            assert agent["max_iter"] == default["max_iter"]

    def test_reset_all_clears_all_llm_overrides(self, seeded_client: TestClient):
        profile = seeded_client.post(
            "/api/v1/admin/llm-profiles", json=_PROFILE_PAYLOAD
        ).json()

        # Assign profile to multiple agents
        for agent_id in ["test_runner", "execution_orchestrator"]:
            seeded_client.put(
                f"/api/v1/admin/agent-configs/{agent_id}",
                json={"llm_profile_id": profile["id"]},
            )

        seeded_client.post("/api/v1/admin/agent-configs/reset-all")

        for agent_id in ["test_runner", "execution_orchestrator"]:
            agent = seeded_client.get(f"/api/v1/admin/agent-configs/{agent_id}").json()
            assert agent["llm_profile_id"] is None


# ─────────────────────────────────────────────────────────────────────────────
# 4. Pipeline
# ─────────────────────────────────────────────────────────────────────────────


class TestPipelineRun:
    def test_run_returns_202_with_run_id(self, seeded_client: TestClient):
        r = seeded_client.post(
            "/api/v1/pipeline/run",
            files={"file": _MD_FILE},
        )
        assert r.status_code == 202
        body = r.json()
        assert "id" in body
        assert body["status"] == "pending"
        assert body["document_name"] == "requirements.md"

    def test_run_response_has_required_fields(self, seeded_client: TestClient):
        r = seeded_client.post(
            "/api/v1/pipeline/run",
            files={"file": _MD_FILE},
        )
        assert r.status_code == 202
        body = r.json()
        assert "id" in body
        assert "status" in body
        assert "document_name" in body
        assert "created_at" in body
        assert "agent_statuses" in body

    def test_run_with_llm_profile_override(self, seeded_client: TestClient):
        profile = seeded_client.post(
            "/api/v1/admin/llm-profiles", json=_PROFILE_PAYLOAD
        ).json()
        r = seeded_client.post(
            "/api/v1/pipeline/run",
            files={"file": _MD_FILE},
            data={"llm_profile_id": str(profile["id"])},
        )
        assert r.status_code == 202
        assert r.json()["llm_profile_id"] == profile["id"]

    def test_run_with_invalid_llm_profile_returns_404(self, seeded_client: TestClient):
        r = seeded_client.post(
            "/api/v1/pipeline/run",
            files={"file": _MD_FILE},
            data={"llm_profile_id": "99999"},
        )
        assert r.status_code == 404

    def test_run_unsupported_file_type(self, seeded_client: TestClient):
        bad_file = ("script.py", io.BytesIO(b"print('hello')"), "text/x-python")
        r = seeded_client.post("/api/v1/pipeline/run", files={"file": bad_file})
        assert r.status_code == 415

    def test_run_no_file_returns_422(self, seeded_client: TestClient):
        r = seeded_client.post("/api/v1/pipeline/run")
        assert r.status_code == 422

    def test_run_pdf_file_accepted(self, seeded_client: TestClient):
        pdf_file = ("spec.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")
        r = seeded_client.post("/api/v1/pipeline/run", files={"file": pdf_file})
        assert r.status_code == 202

    def test_run_txt_file_accepted(self, seeded_client: TestClient):
        txt_file = ("spec.txt", io.BytesIO(b"Requirements text"), "text/plain")
        r = seeded_client.post("/api/v1/pipeline/run", files={"file": txt_file})
        assert r.status_code == 202

    def test_run_with_skip_execution_flag(self, seeded_client: TestClient):
        r = seeded_client.post(
            "/api/v1/pipeline/run",
            files={"file": _MD_FILE},
            data={"skip_execution": "true"},
        )
        assert r.status_code == 202

    def test_run_with_environment_param(self, seeded_client: TestClient):
        r = seeded_client.post(
            "/api/v1/pipeline/run",
            files={"file": _MD_FILE},
            data={"environment": "staging"},
        )
        assert r.status_code == 202

    def test_run_creates_unique_ids(self, seeded_client: TestClient):
        ids = set()
        for _ in range(3):
            r = seeded_client.post(
                "/api/v1/pipeline/run",
                files={"file": _MD_FILE},
            )
            assert r.status_code == 202
            ids.add(r.json()["id"])
        assert len(ids) == 3  # all unique


class TestPipelineList:
    def test_list_empty(self, seeded_client: TestClient):
        r = seeded_client.get("/api/v1/pipeline/runs")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 0
        assert body["items"] == []
        assert body["page"] == 1

    def test_list_after_creating_runs(self, seeded_client: TestClient):
        for _ in range(3):
            seeded_client.post("/api/v1/pipeline/run", files={"file": _MD_FILE})

        r = seeded_client.get("/api/v1/pipeline/runs")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 3
        assert len(body["items"]) == 3

    def test_list_pagination(self, seeded_client: TestClient):
        for _ in range(5):
            seeded_client.post("/api/v1/pipeline/run", files={"file": _MD_FILE})

        r = seeded_client.get("/api/v1/pipeline/runs?page=1&page_size=2")
        assert r.status_code == 200
        body = r.json()
        assert len(body["items"]) == 2
        assert body["total"] == 5
        assert body["page"] == 1
        assert body["page_size"] == 2

    def test_list_page_2(self, seeded_client: TestClient):
        for _ in range(5):
            seeded_client.post("/api/v1/pipeline/run", files={"file": _MD_FILE})

        r = seeded_client.get("/api/v1/pipeline/runs?page=2&page_size=2")
        assert r.status_code == 200
        body = r.json()
        assert len(body["items"]) == 2  # items 3 and 4

    def test_list_filter_by_status_pending(self, seeded_client: TestClient):
        seeded_client.post("/api/v1/pipeline/run", files={"file": _MD_FILE})
        r = seeded_client.get("/api/v1/pipeline/runs?status=pending")
        assert r.status_code == 200
        body = r.json()
        assert all(item["status"] == "pending" for item in body["items"])

    def test_list_filter_invalid_status_returns_422(self, seeded_client: TestClient):
        r = seeded_client.get("/api/v1/pipeline/runs?status=invalid_status")
        assert r.status_code == 422

    def test_list_items_have_required_fields(self, seeded_client: TestClient):
        seeded_client.post("/api/v1/pipeline/run", files={"file": _MD_FILE})
        r = seeded_client.get("/api/v1/pipeline/runs")
        for item in r.json()["items"]:
            assert "id" in item
            assert "document_name" in item
            assert "status" in item
            assert "created_at" in item

    def test_list_newest_first(self, seeded_client: TestClient):
        ids = []
        for _ in range(3):
            r = seeded_client.post("/api/v1/pipeline/run", files={"file": _MD_FILE})
            ids.append(r.json()["id"])

        r = seeded_client.get("/api/v1/pipeline/runs")
        returned_ids = [item["id"] for item in r.json()["items"]]
        # newest first means reversed insertion order
        assert returned_ids[0] == ids[-1]


class TestPipelineGetDetail:
    def test_get_existing_run(self, seeded_client: TestClient):
        created = seeded_client.post(
            "/api/v1/pipeline/run", files={"file": _MD_FILE}
        ).json()
        r = seeded_client.get(f"/api/v1/pipeline/runs/{created['id']}")
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == created["id"]
        assert body["document_name"] == "requirements.md"

    def test_get_not_found(self, seeded_client: TestClient):
        fake_id = str(uuid.uuid4())
        r = seeded_client.get(f"/api/v1/pipeline/runs/{fake_id}")
        assert r.status_code == 404

    def test_get_includes_results_by_default(self, seeded_client: TestClient):
        created = seeded_client.post(
            "/api/v1/pipeline/run", files={"file": _MD_FILE}
        ).json()
        r = seeded_client.get(f"/api/v1/pipeline/runs/{created['id']}")
        assert r.status_code == 200
        assert "results" in r.json()

    def test_get_exclude_results(self, seeded_client: TestClient):
        created = seeded_client.post(
            "/api/v1/pipeline/run", files={"file": _MD_FILE}
        ).json()
        r = seeded_client.get(
            f"/api/v1/pipeline/runs/{created['id']}?include_results=false"
        )
        assert r.status_code == 200
        assert "results" not in r.json()

    def test_get_includes_agent_statuses(self, seeded_client: TestClient):
        created = seeded_client.post(
            "/api/v1/pipeline/run", files={"file": _MD_FILE}
        ).json()
        r = seeded_client.get(f"/api/v1/pipeline/runs/{created['id']}")
        body = r.json()
        assert "agent_statuses" in body
        assert isinstance(body["agent_statuses"], dict)


class TestPipelineDelete:
    def test_delete_existing_run(self, seeded_client: TestClient):
        created = seeded_client.post(
            "/api/v1/pipeline/run", files={"file": _MD_FILE}
        ).json()
        r = seeded_client.delete(f"/api/v1/pipeline/runs/{created['id']}")
        assert r.status_code == 204

    def test_delete_removes_from_list(self, seeded_client: TestClient):
        created = seeded_client.post(
            "/api/v1/pipeline/run", files={"file": _MD_FILE}
        ).json()
        seeded_client.delete(f"/api/v1/pipeline/runs/{created['id']}")
        r = seeded_client.get("/api/v1/pipeline/runs")
        assert r.json()["total"] == 0

    def test_delete_not_found(self, seeded_client: TestClient):
        r = seeded_client.delete(f"/api/v1/pipeline/runs/{uuid.uuid4()}")
        assert r.status_code == 404

    def test_delete_makes_get_return_404(self, seeded_client: TestClient):
        created = seeded_client.post(
            "/api/v1/pipeline/run", files={"file": _MD_FILE}
        ).json()
        seeded_client.delete(f"/api/v1/pipeline/runs/{created['id']}")
        r = seeded_client.get(f"/api/v1/pipeline/runs/{created['id']}")
        assert r.status_code == 404


class TestPipelineCancel:
    def test_cancel_pending_run(self, seeded_client: TestClient):
        created = seeded_client.post(
            "/api/v1/pipeline/run", files={"file": _MD_FILE}
        ).json()
        # Newly created run is in 'pending' state
        r = seeded_client.post(f"/api/v1/pipeline/runs/{created['id']}/cancel")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "failed"
        assert "cancelled" in (body.get("error") or "").lower()

    def test_cancel_not_found(self, seeded_client: TestClient):
        r = seeded_client.post(f"/api/v1/pipeline/runs/{uuid.uuid4()}/cancel")
        assert r.status_code == 404

    def test_cancel_completed_run_returns_409(self, seeded_client: TestClient, db):
        """A completed run cannot be cancelled."""
        from app.db import crud
        from app.schemas.pipeline import PipelineStatus

        created = seeded_client.post(
            "/api/v1/pipeline/run", files={"file": _MD_FILE}
        ).json()
        # Manually set to completed
        crud.update_pipeline_run_status(db, created["id"], PipelineStatus.COMPLETED)
        db.commit()

        r = seeded_client.post(f"/api/v1/pipeline/runs/{created['id']}/cancel")
        assert r.status_code == 409

    def test_cancel_failed_run_returns_409(self, seeded_client: TestClient, db):
        from app.db import crud
        from app.schemas.pipeline import PipelineStatus

        created = seeded_client.post(
            "/api/v1/pipeline/run", files={"file": _MD_FILE}
        ).json()
        crud.update_pipeline_run_status(
            db, created["id"], PipelineStatus.FAILED, error="Previous failure"
        )
        db.commit()

        r = seeded_client.post(f"/api/v1/pipeline/runs/{created['id']}/cancel")
        assert r.status_code == 409


class TestPipelineResults:
    def test_get_results_empty(self, seeded_client: TestClient):
        created = seeded_client.post(
            "/api/v1/pipeline/run", files={"file": _MD_FILE}
        ).json()
        r = seeded_client.get(f"/api/v1/pipeline/runs/{created['id']}/results")
        assert r.status_code == 200
        assert r.json() == []

    def test_get_results_not_found_run(self, seeded_client: TestClient):
        r = seeded_client.get(f"/api/v1/pipeline/runs/{uuid.uuid4()}/results")
        assert r.status_code == 404

    def test_get_results_with_seeded_data(self, seeded_client: TestClient, db):
        from app.db import crud

        created = seeded_client.post(
            "/api/v1/pipeline/run", files={"file": _MD_FILE}
        ).json()
        run_id = created["id"]

        # Directly insert a result into the DB
        crud.create_pipeline_result(
            db,
            run_id=run_id,
            stage="testcase",
            agent_id="requirement_analyzer",
            output={"parsed": True, "requirements": ["REQ-001"]},
        )
        db.commit()

        r = seeded_client.get(f"/api/v1/pipeline/runs/{run_id}/results")
        assert r.status_code == 200
        results = r.json()
        assert len(results) == 1
        assert results[0]["agent_id"] == "requirement_analyzer"
        assert results[0]["stage"] == "testcase"
        assert results[0]["output"] == {"parsed": True, "requirements": ["REQ-001"]}

    def test_get_results_filter_by_stage(self, seeded_client: TestClient, db):
        from app.db import crud

        created = seeded_client.post(
            "/api/v1/pipeline/run", files={"file": _MD_FILE}
        ).json()
        run_id = created["id"]

        crud.create_pipeline_result(
            db, run_id=run_id, stage="testcase", agent_id="agent_a", output={"x": 1}
        )
        crud.create_pipeline_result(
            db, run_id=run_id, stage="reporting", agent_id="agent_b", output={"y": 2}
        )
        db.commit()

        r = seeded_client.get(f"/api/v1/pipeline/runs/{run_id}/results?stage=testcase")
        assert r.status_code == 200
        results = r.json()
        assert len(results) == 1
        assert results[0]["stage"] == "testcase"

    def test_get_results_filter_by_agent_id(self, seeded_client: TestClient, db):
        from app.db import crud

        created = seeded_client.post(
            "/api/v1/pipeline/run", files={"file": _MD_FILE}
        ).json()
        run_id = created["id"]

        crud.create_pipeline_result(
            db,
            run_id=run_id,
            stage="testcase",
            agent_id="target_agent",
            output={"a": 1},
        )
        crud.create_pipeline_result(
            db, run_id=run_id, stage="testcase", agent_id="other_agent", output={"b": 2}
        )
        db.commit()

        r = seeded_client.get(
            f"/api/v1/pipeline/runs/{run_id}/results?agent_id=target_agent"
        )
        assert r.status_code == 200
        results = r.json()
        assert len(results) == 1
        assert results[0]["agent_id"] == "target_agent"

    def test_results_included_in_run_detail(self, seeded_client: TestClient, db):
        from app.db import crud

        created = seeded_client.post(
            "/api/v1/pipeline/run", files={"file": _MD_FILE}
        ).json()
        run_id = created["id"]

        crud.create_pipeline_result(
            db, run_id=run_id, stage="ingestion", agent_id="chunker", output="chunked"
        )
        db.commit()

        r = seeded_client.get(f"/api/v1/pipeline/runs/{run_id}")
        assert r.status_code == 200
        body = r.json()
        assert len(body["results"]) == 1
        assert body["results"][0]["agent_id"] == "chunker"


# ─────────────────────────────────────────────────────────────────────────────
# 5. WebSocket
# ─────────────────────────────────────────────────────────────────────────────


class TestWebSocket:
    def test_connect_receives_greeting(self, client: TestClient):
        run_id = str(uuid.uuid4())
        with client.websocket_connect(f"/ws/pipeline/{run_id}") as ws:
            msg = json.loads(ws.receive_text())
            assert msg["event"] == "connected"
            assert msg["run_id"] == run_id
            assert "timestamp" in msg
            assert "data" in msg

    def test_ping_receives_pong(self, client: TestClient):
        run_id = str(uuid.uuid4())
        with client.websocket_connect(f"/ws/pipeline/{run_id}") as ws:
            ws.receive_text()  # consume greeting
            ws.send_text(json.dumps({"action": "ping"}))
            msg = json.loads(ws.receive_text())
            assert msg["event"] == "pong"
            assert msg["run_id"] == run_id

    def test_multiple_ws_connections_same_run(self, client: TestClient):
        run_id = str(uuid.uuid4())
        with client.websocket_connect(f"/ws/pipeline/{run_id}") as ws1:
            with client.websocket_connect(f"/ws/pipeline/{run_id}") as ws2:
                greeting1 = json.loads(ws1.receive_text())
                greeting2 = json.loads(ws2.receive_text())
                assert greeting1["run_id"] == run_id
                assert greeting2["run_id"] == run_id

    def test_ws_different_run_ids(self, client: TestClient):
        run_id_a = str(uuid.uuid4())
        run_id_b = str(uuid.uuid4())
        with client.websocket_connect(f"/ws/pipeline/{run_id_a}") as ws_a:
            with client.websocket_connect(f"/ws/pipeline/{run_id_b}") as ws_b:
                msg_a = json.loads(ws_a.receive_text())
                msg_b = json.loads(ws_b.receive_text())
                assert msg_a["run_id"] == run_id_a
                assert msg_b["run_id"] == run_id_b
                assert msg_a["run_id"] != msg_b["run_id"]

    def test_ws_greeting_has_timestamp(self, client: TestClient):
        run_id = str(uuid.uuid4())
        with client.websocket_connect(f"/ws/pipeline/{run_id}") as ws:
            msg = json.loads(ws.receive_text())
            assert "timestamp" in msg
            # Should be a valid ISO timestamp string
            assert "T" in msg["timestamp"]

    def test_ws_unknown_message_ignored(self, client: TestClient):
        """Sending unknown messages should not crash the server."""
        run_id = str(uuid.uuid4())
        with client.websocket_connect(f"/ws/pipeline/{run_id}") as ws:
            ws.receive_text()  # greeting
            ws.send_text("not-json")
            ws.send_text(json.dumps({"action": "unknown"}))
            # No crash — sending ping should still work
            ws.send_text(json.dumps({"action": "ping"}))
            msg = json.loads(ws.receive_text())
            assert msg["event"] == "pong"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Cross-cutting / Integration scenarios
# ─────────────────────────────────────────────────────────────────────────────


class TestIntegration:
    def test_run_then_get_then_delete_lifecycle(self, seeded_client: TestClient):
        # Create
        r = seeded_client.post("/api/v1/pipeline/run", files={"file": _MD_FILE})
        assert r.status_code == 202
        run_id = r.json()["id"]

        # Get
        r = seeded_client.get(f"/api/v1/pipeline/runs/{run_id}")
        assert r.status_code == 200

        # Appears in list
        r = seeded_client.get("/api/v1/pipeline/runs")
        assert any(item["id"] == run_id for item in r.json()["items"])

        # Delete
        r = seeded_client.delete(f"/api/v1/pipeline/runs/{run_id}")
        assert r.status_code == 204

        # Gone from list
        r = seeded_client.get("/api/v1/pipeline/runs")
        assert not any(item["id"] == run_id for item in r.json()["items"])

    def test_llm_profile_assigned_to_agent_then_deleted_sets_null(
        self, seeded_client: TestClient
    ):
        """
        Deleting an LLM profile should set agent's llm_profile_id to NULL
        (FK ondelete=SET NULL), not cascade-delete the agent.
        """
        profile = seeded_client.post(
            "/api/v1/admin/llm-profiles", json=_PROFILE_PAYLOAD
        ).json()
        seeded_client.put(
            "/api/v1/admin/agent-configs/requirement_analyzer",
            json={"llm_profile_id": profile["id"]},
        )

        # Confirm the override is set
        agent = seeded_client.get(
            "/api/v1/admin/agent-configs/requirement_analyzer"
        ).json()
        assert agent["llm_profile_id"] == profile["id"]

        # Delete the profile
        seeded_client.delete(f"/api/v1/admin/llm-profiles/{profile['id']}")

        # Agent should still exist with llm_profile_id = None
        agent_after = seeded_client.get(
            "/api/v1/admin/agent-configs/requirement_analyzer"
        ).json()
        assert agent_after["agent_id"] == "requirement_analyzer"
        assert agent_after["llm_profile_id"] is None

    def test_concurrent_run_limit_enforced(self, seeded_client: TestClient, db):
        """
        When MAX_CONCURRENT_RUNS is reached, a new run should be rejected with 429.
        """
        from app.config import settings
        from app.db import crud
        from app.schemas.pipeline import PipelineStatus

        # Manually create running runs up to the limit
        for i in range(settings.MAX_CONCURRENT_RUNS):
            run = crud.create_pipeline_run(
                db, document_name=f"doc{i}.md", document_path=f"/tmp/doc{i}.md"
            )
            crud.update_pipeline_run_status(db, run.id, PipelineStatus.RUNNING)
        db.commit()

        # Next run should be rejected
        r = seeded_client.post("/api/v1/pipeline/run", files={"file": _MD_FILE})
        assert r.status_code == 429

    def test_openapi_schema_is_accessible(self, client: TestClient):
        r = client.get("/openapi.json")
        assert r.status_code == 200
        schema = r.json()
        assert "paths" in schema
        assert "/api/v1/pipeline/run" in schema["paths"]
        assert "/api/v1/admin/llm-profiles" in schema["paths"]
        assert "/api/v1/admin/agent-configs" in schema["paths"]

    def test_docs_ui_accessible(self, client: TestClient):
        r = client.get("/docs")
        assert r.status_code == 200

    def test_redoc_ui_accessible(self, client: TestClient):
        r = client.get("/redoc")
        assert r.status_code == 200

    def test_root_returns_message(self, client: TestClient):
        r = client.get("/")
        assert r.status_code == 200
        body = r.json()
        assert "message" in body
        assert "docs" in body
