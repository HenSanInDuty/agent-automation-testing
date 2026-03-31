"""
tests/test_crud.py
──────────────────
Unit tests for LLMProfile and AgentConfig CRUD operations.

Uses an in-memory SQLite database so tests are fast, isolated, and require
no external services. Each test function gets a fresh DB via the `db` fixture.

Run:
    cd backend
    uv run pytest tests/test_crud.py -v
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# ── Bootstrap an in-memory DB before importing app modules ────────────────────
# (prevents the app from trying to create the real sqlite file during import)

TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)
TestSessionLocal = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="function")
def db() -> Session:
    """
    Yield a fresh in-memory DB session for each test.
    Tables are created before the test and dropped afterwards.
    """
    # Import models so they register on Base.metadata
    from app.db import models  # noqa: F401 – registers all ORM classes
    from app.db.database import Base

    Base.metadata.create_all(bind=test_engine)

    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def sample_profile_payload():
    """A minimal LLMProfileCreate payload."""
    from app.schemas.llm_profile import LLMProfileCreate, LLMProvider

    return LLMProfileCreate(
        name="Test GPT-4o",
        provider=LLMProvider.OPENAI,
        model="gpt-4o",
        api_key="sk-test-1234",
        base_url=None,
        temperature=0.1,
        max_tokens=2048,
        is_default=False,
    )


@pytest.fixture()
def seeded_profile(db: Session, sample_profile_payload):
    """An LLMProfile already persisted to the DB."""
    from app.db.crud import create_llm_profile

    return create_llm_profile(db, sample_profile_payload)


# ─────────────────────────────────────────────────────────────────────────────
# LLMProfile – CREATE
# ─────────────────────────────────────────────────────────────────────────────


class TestCreateLLMProfile:
    def test_creates_profile_with_correct_fields(self, db, sample_profile_payload):
        from app.db.crud import create_llm_profile

        profile = create_llm_profile(db, sample_profile_payload)

        assert profile.id is not None
        assert profile.name == "Test GPT-4o"
        assert profile.provider == "openai"
        assert profile.model == "gpt-4o"
        assert profile.api_key == "sk-test-1234"
        assert profile.temperature == 0.1
        assert profile.max_tokens == 2048
        assert profile.is_default is False

    def test_creates_default_profile_and_clears_others(self, db):
        from app.db.crud import create_llm_profile
        from app.schemas.llm_profile import LLMProfileCreate, LLMProvider

        first = create_llm_profile(
            db,
            LLMProfileCreate(
                name="First",
                provider=LLMProvider.OPENAI,
                model="gpt-4o",
                is_default=True,
            ),
        )
        assert first.is_default is True

        second = create_llm_profile(
            db,
            LLMProfileCreate(
                name="Second",
                provider=LLMProvider.ANTHROPIC,
                model="claude-3-5-sonnet-20241022",
                is_default=True,
            ),
        )

        # Refresh first from DB to see the updated value
        db.refresh(first)
        assert second.is_default is True
        assert first.is_default is False

    def test_two_profiles_can_be_non_default(self, db):
        from app.db.crud import create_llm_profile
        from app.schemas.llm_profile import LLMProfileCreate, LLMProvider

        p1 = create_llm_profile(
            db,
            LLMProfileCreate(
                name="A", provider=LLMProvider.OPENAI, model="gpt-4o", is_default=False
            ),
        )
        p2 = create_llm_profile(
            db,
            LLMProfileCreate(
                name="B",
                provider=LLMProvider.OLLAMA,
                model="llama3",
                is_default=False,
            ),
        )

        assert p1.is_default is False
        assert p2.is_default is False

    def test_timestamps_are_set_on_create(self, db, sample_profile_payload):
        from app.db.crud import create_llm_profile

        profile = create_llm_profile(db, sample_profile_payload)

        assert profile.created_at is not None
        assert profile.updated_at is not None


# ─────────────────────────────────────────────────────────────────────────────
# LLMProfile – READ
# ─────────────────────────────────────────────────────────────────────────────


class TestReadLLMProfile:
    def test_get_by_id_returns_correct_profile(self, db, seeded_profile):
        from app.db.crud import get_llm_profile

        found = get_llm_profile(db, seeded_profile.id)

        assert found is not None
        assert found.id == seeded_profile.id
        assert found.name == seeded_profile.name

    def test_get_by_id_returns_none_for_missing(self, db):
        from app.db.crud import get_llm_profile

        assert get_llm_profile(db, 9999) is None

    def test_get_by_name_returns_correct_profile(self, db, seeded_profile):
        from app.db.crud import get_llm_profile_by_name

        found = get_llm_profile_by_name(db, "Test GPT-4o")

        assert found is not None
        assert found.id == seeded_profile.id

    def test_get_by_name_returns_none_for_missing(self, db):
        from app.db.crud import get_llm_profile_by_name

        assert get_llm_profile_by_name(db, "Does Not Exist") is None

    def test_get_all_returns_all_profiles(self, db):
        from app.db.crud import create_llm_profile, get_all_llm_profiles
        from app.schemas.llm_profile import LLMProfileCreate, LLMProvider

        for i in range(3):
            create_llm_profile(
                db,
                LLMProfileCreate(
                    name=f"Profile {i}",
                    provider=LLMProvider.OPENAI,
                    model="gpt-4o",
                ),
            )

        items, total = get_all_llm_profiles(db)

        assert total == 3
        assert len(items) == 3

    def test_get_all_pagination(self, db):
        from app.db.crud import create_llm_profile, get_all_llm_profiles
        from app.schemas.llm_profile import LLMProfileCreate, LLMProvider

        for i in range(5):
            create_llm_profile(
                db,
                LLMProfileCreate(
                    name=f"Profile {i}",
                    provider=LLMProvider.OPENAI,
                    model="gpt-4o",
                ),
            )

        items, total = get_all_llm_profiles(db, skip=2, limit=2)

        assert total == 5
        assert len(items) == 2

    def test_get_default_returns_default_profile(self, db):
        from app.db.crud import create_llm_profile, get_default_llm_profile
        from app.schemas.llm_profile import LLMProfileCreate, LLMProvider

        create_llm_profile(
            db,
            LLMProfileCreate(
                name="Not Default",
                provider=LLMProvider.OPENAI,
                model="gpt-4o",
                is_default=False,
            ),
        )
        default = create_llm_profile(
            db,
            LLMProfileCreate(
                name="Default One",
                provider=LLMProvider.ANTHROPIC,
                model="claude-3-5-sonnet-20241022",
                is_default=True,
            ),
        )

        found = get_default_llm_profile(db)

        assert found is not None
        assert found.id == default.id

    def test_get_default_returns_none_when_none_set(self, db):
        from app.db.crud import get_default_llm_profile

        assert get_default_llm_profile(db) is None


# ─────────────────────────────────────────────────────────────────────────────
# LLMProfile – UPDATE
# ─────────────────────────────────────────────────────────────────────────────


class TestUpdateLLMProfile:
    def test_partial_update_changes_only_supplied_fields(self, db, seeded_profile):
        from app.db.crud import update_llm_profile
        from app.schemas.llm_profile import LLMProfileUpdate

        updated = update_llm_profile(
            db,
            seeded_profile.id,
            LLMProfileUpdate(model="gpt-4o-mini"),
        )

        assert updated is not None
        assert updated.model == "gpt-4o-mini"
        # name and temperature should be unchanged
        assert updated.name == "Test GPT-4o"
        assert updated.temperature == 0.1

    def test_update_api_key(self, db, seeded_profile):
        from app.db.crud import update_llm_profile
        from app.schemas.llm_profile import LLMProfileUpdate

        updated = update_llm_profile(
            db,
            seeded_profile.id,
            LLMProfileUpdate(api_key="sk-new-key"),
        )

        assert updated is not None
        assert updated.api_key == "sk-new-key"

    def test_update_returns_none_for_missing_id(self, db):
        from app.db.crud import update_llm_profile
        from app.schemas.llm_profile import LLMProfileUpdate

        result = update_llm_profile(db, 9999, LLMProfileUpdate(model="gpt-4o"))

        assert result is None

    def test_update_set_default_clears_others(self, db):
        from app.db.crud import create_llm_profile, update_llm_profile
        from app.schemas.llm_profile import (
            LLMProfileCreate,
            LLMProfileUpdate,
            LLMProvider,
        )

        p1 = create_llm_profile(
            db,
            LLMProfileCreate(
                name="Alpha",
                provider=LLMProvider.OPENAI,
                model="gpt-4o",
                is_default=True,
            ),
        )
        p2 = create_llm_profile(
            db,
            LLMProfileCreate(
                name="Beta",
                provider=LLMProvider.ANTHROPIC,
                model="claude-3-5-sonnet-20241022",
                is_default=False,
            ),
        )

        update_llm_profile(db, p2.id, LLMProfileUpdate(is_default=True))
        db.refresh(p1)
        db.refresh(p2)

        assert p2.is_default is True
        assert p1.is_default is False


# ─────────────────────────────────────────────────────────────────────────────
# LLMProfile – DELETE & SET DEFAULT
# ─────────────────────────────────────────────────────────────────────────────


class TestDeleteAndSetDefault:
    def test_delete_removes_profile(self, db, seeded_profile):
        from app.db.crud import delete_llm_profile, get_llm_profile

        result = delete_llm_profile(db, seeded_profile.id)

        assert result is True
        assert get_llm_profile(db, seeded_profile.id) is None

    def test_delete_returns_false_for_missing(self, db):
        from app.db.crud import delete_llm_profile

        assert delete_llm_profile(db, 9999) is False

    def test_set_default_marks_profile_as_default(self, db, seeded_profile):
        from app.db.crud import set_default_llm_profile

        result = set_default_llm_profile(db, seeded_profile.id)

        assert result is not None
        assert result.is_default is True

    def test_set_default_returns_none_for_missing(self, db):
        from app.db.crud import set_default_llm_profile

        assert set_default_llm_profile(db, 9999) is None


# ─────────────────────────────────────────────────────────────────────────────
# AgentConfig – helpers
# ─────────────────────────────────────────────────────────────────────────────


def _insert_agent(
    db: Session, agent_id: str = "requirement_analyzer", stage: str = "testcase"
):
    """Helper: insert a minimal AgentConfig directly via ORM."""
    from app.db.models import AgentConfig

    config = AgentConfig(
        agent_id=agent_id,
        display_name=agent_id.replace("_", " ").title(),
        stage=stage,
        role="Test Role",
        goal="Test Goal",
        backstory="Test Backstory",
        enabled=True,
        verbose=False,
        max_iter=5,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


# ─────────────────────────────────────────────────────────────────────────────
# AgentConfig – READ
# ─────────────────────────────────────────────────────────────────────────────


class TestReadAgentConfig:
    def test_get_by_agent_id_returns_correct_config(self, db):
        from app.db.crud import get_agent_config

        _insert_agent(db, "requirement_analyzer")

        config = get_agent_config(db, "requirement_analyzer")

        assert config is not None
        assert config.agent_id == "requirement_analyzer"
        assert config.stage == "testcase"

    def test_get_by_agent_id_returns_none_for_missing(self, db):
        from app.db.crud import get_agent_config

        assert get_agent_config(db, "nonexistent_agent") is None

    def test_get_all_returns_all_configs(self, db):
        from app.db.crud import get_all_agent_configs

        _insert_agent(db, "requirement_analyzer", "testcase")
        _insert_agent(db, "execution_orchestrator", "execution")

        configs = get_all_agent_configs(db)

        assert len(configs) == 2

    def test_get_all_filters_by_stage(self, db):
        from app.db.crud import get_all_agent_configs

        _insert_agent(db, "requirement_analyzer", "testcase")
        _insert_agent(db, "rule_parser", "testcase")
        _insert_agent(db, "execution_orchestrator", "execution")

        testcase_configs = get_all_agent_configs(db, stage="testcase")
        execution_configs = get_all_agent_configs(db, stage="execution")

        assert len(testcase_configs) == 2
        assert len(execution_configs) == 1

    def test_get_all_filters_enabled_only(self, db):
        from app.db.crud import get_all_agent_configs
        from app.db.models import AgentConfig

        _insert_agent(db, "active_agent", "testcase")

        # Insert a disabled agent directly
        disabled = AgentConfig(
            agent_id="disabled_agent",
            display_name="Disabled",
            stage="testcase",
            role="r",
            goal="g",
            backstory="b",
            enabled=False,
        )
        db.add(disabled)
        db.commit()

        configs = get_all_agent_configs(db, enabled_only=True)

        agent_ids = [c.agent_id for c in configs]
        assert "active_agent" in agent_ids
        assert "disabled_agent" not in agent_ids


# ─────────────────────────────────────────────────────────────────────────────
# AgentConfig – UPDATE
# ─────────────────────────────────────────────────────────────────────────────


class TestUpdateAgentConfig:
    def test_partial_update_changes_only_supplied_fields(self, db):
        from app.db.crud import update_agent_config
        from app.schemas.agent_config import AgentConfigUpdate

        _insert_agent(db, "requirement_analyzer")

        updated = update_agent_config(
            db,
            "requirement_analyzer",
            AgentConfigUpdate(role="Updated Role"),
        )

        assert updated is not None
        assert updated.role == "Updated Role"
        assert updated.goal == "Test Goal"  # unchanged
        assert updated.backstory == "Test Backstory"  # unchanged

    def test_update_verbose_flag(self, db):
        from app.db.crud import update_agent_config
        from app.schemas.agent_config import AgentConfigUpdate

        _insert_agent(db)

        updated = update_agent_config(
            db,
            "requirement_analyzer",
            AgentConfigUpdate(verbose=True),
        )

        assert updated is not None
        assert updated.verbose is True

    def test_update_returns_none_for_missing_agent(self, db):
        from app.db.crud import update_agent_config
        from app.schemas.agent_config import AgentConfigUpdate

        result = update_agent_config(
            db,
            "nonexistent_agent",
            AgentConfigUpdate(role="New Role"),
        )

        assert result is None

    def test_update_llm_profile_id(self, db, seeded_profile):
        from app.db.crud import update_agent_config
        from app.schemas.agent_config import AgentConfigUpdate

        _insert_agent(db)

        updated = update_agent_config(
            db,
            "requirement_analyzer",
            AgentConfigUpdate(llm_profile_id=seeded_profile.id),
        )

        assert updated is not None
        assert updated.llm_profile_id == seeded_profile.id

    def test_update_max_iter(self, db):
        from app.db.crud import update_agent_config
        from app.schemas.agent_config import AgentConfigUpdate

        _insert_agent(db)

        updated = update_agent_config(
            db,
            "requirement_analyzer",
            AgentConfigUpdate(max_iter=10),
        )

        assert updated is not None
        assert updated.max_iter == 10


# ─────────────────────────────────────────────────────────────────────────────
# AgentConfig – UPSERT (used by seeder)
# ─────────────────────────────────────────────────────────────────────────────


class TestUpsertAgentConfig:
    def test_inserts_new_config(self, db):
        from app.db.crud import get_agent_config, upsert_agent_config

        upsert_agent_config(
            db,
            {
                "agent_id": "new_agent",
                "display_name": "New Agent",
                "stage": "testcase",
                "role": "Role",
                "goal": "Goal",
                "backstory": "Backstory",
            },
        )

        config = get_agent_config(db, "new_agent")
        assert config is not None
        assert config.display_name == "New Agent"

    def test_does_not_overwrite_existing(self, db):
        from app.db.crud import (
            get_agent_config,
            update_agent_config,
            upsert_agent_config,
        )
        from app.schemas.agent_config import AgentConfigUpdate

        # Seed initial config
        upsert_agent_config(
            db,
            {
                "agent_id": "existing_agent",
                "display_name": "Original Name",
                "stage": "testcase",
                "role": "Role",
                "goal": "Goal",
                "backstory": "Backstory",
            },
        )

        # Simulate user customisation
        update_agent_config(db, "existing_agent", AgentConfigUpdate(role="Custom Role"))

        # Call upsert again — should NOT overwrite user's custom role
        upsert_agent_config(
            db,
            {
                "agent_id": "existing_agent",
                "display_name": "New Name",
                "stage": "testcase",
                "role": "Default Role",
                "goal": "Goal",
                "backstory": "Backstory",
            },
        )

        config = get_agent_config(db, "existing_agent")
        assert config is not None
        assert config.role == "Custom Role"  # preserved


# ─────────────────────────────────────────────────────────────────────────────
# AgentConfig – RESET
# ─────────────────────────────────────────────────────────────────────────────


class TestResetAgentConfig:
    def test_reset_restores_default_values(self, db):
        from app.db.crud import reset_agent_config, update_agent_config
        from app.schemas.agent_config import AgentConfigUpdate

        _insert_agent(db)

        # Customise
        update_agent_config(
            db,
            "requirement_analyzer",
            AgentConfigUpdate(role="Custom Role", max_iter=20),
        )

        defaults = {
            "display_name": "Requirement Analyzer",
            "stage": "testcase",
            "role": "Test Role",
            "goal": "Test Goal",
            "backstory": "Test Backstory",
            "enabled": True,
            "verbose": False,
            "max_iter": 5,
        }
        reset_config = reset_agent_config(db, "requirement_analyzer", defaults)

        assert reset_config is not None
        assert reset_config.role == "Test Role"
        assert reset_config.max_iter == 5

    def test_reset_clears_llm_profile_override(self, db, seeded_profile):
        from app.db.crud import reset_agent_config, update_agent_config
        from app.schemas.agent_config import AgentConfigUpdate

        _insert_agent(db)

        # Set a per-agent LLM override
        update_agent_config(
            db,
            "requirement_analyzer",
            AgentConfigUpdate(llm_profile_id=seeded_profile.id),
        )

        reset_config = reset_agent_config(
            db,
            "requirement_analyzer",
            {
                "role": "Test Role",
                "goal": "Test Goal",
                "backstory": "Test Backstory",
                "enabled": True,
                "verbose": False,
                "max_iter": 5,
            },
        )

        assert reset_config is not None
        assert reset_config.llm_profile_id is None  # cleared

    def test_reset_returns_none_for_missing_agent(self, db):
        from app.db.crud import reset_agent_config

        result = reset_agent_config(db, "nonexistent", {"role": "r"})
        assert result is None

    def test_reset_all_restores_all_agents(self, db):
        from app.db.crud import reset_all_agent_configs, update_agent_config
        from app.schemas.agent_config import AgentConfigUpdate

        _insert_agent(db, "requirement_analyzer", "testcase")
        _insert_agent(db, "rule_parser", "testcase")

        # Customise both
        update_agent_config(db, "requirement_analyzer", AgentConfigUpdate(max_iter=50))
        update_agent_config(db, "rule_parser", AgentConfigUpdate(verbose=True))

        defaults = [
            {
                "agent_id": "requirement_analyzer",
                "role": "r",
                "goal": "g",
                "backstory": "b",
                "enabled": True,
                "verbose": False,
                "max_iter": 5,
            },
            {
                "agent_id": "rule_parser",
                "role": "r",
                "goal": "g",
                "backstory": "b",
                "enabled": True,
                "verbose": False,
                "max_iter": 5,
            },
        ]

        configs = reset_all_agent_configs(db, defaults)
        config_map = {c.agent_id: c for c in configs}

        assert config_map["requirement_analyzer"].max_iter == 5
        assert config_map["rule_parser"].verbose is False


# ─────────────────────────────────────────────────────────────────────────────
# Seeder – integration smoke test
# ─────────────────────────────────────────────────────────────────────────────


class TestSeeder:
    def test_seed_all_inserts_llm_profile_and_agents(self, db):
        from app.db.crud import get_all_agent_configs, get_default_llm_profile
        from app.db.seed import seed_all

        seed_all(db)

        default_profile = get_default_llm_profile(db)
        assert default_profile is not None
        assert default_profile.name == "GPT-4o (Default)"
        assert default_profile.is_default is True

        configs = get_all_agent_configs(db)
        assert len(configs) == 18

    def test_seed_all_is_idempotent(self, db):
        from app.db.crud import get_all_agent_configs, get_all_llm_profiles
        from app.db.seed import seed_all

        seed_all(db)
        seed_all(db)  # second call must not duplicate rows

        _, profile_total = get_all_llm_profiles(db)
        configs = get_all_agent_configs(db)

        assert profile_total == 1
        assert len(configs) == 18

    def test_seed_all_covers_all_stages(self, db):
        from app.db.crud import get_all_agent_configs
        from app.db.seed import seed_all

        seed_all(db)

        configs = get_all_agent_configs(db)
        stages = {c.stage for c in configs}

        assert "testcase" in stages
        assert "execution" in stages
        assert "reporting" in stages

    def test_seeded_agents_have_non_empty_prompts(self, db):
        from app.db.crud import get_all_agent_configs
        from app.db.seed import seed_all

        seed_all(db)

        for config in get_all_agent_configs(db):
            assert config.role.strip(), f"Agent {config.agent_id} has empty role"
            assert config.goal.strip(), f"Agent {config.agent_id} has empty goal"
            assert config.backstory.strip(), (
                f"Agent {config.agent_id} has empty backstory"
            )

    def test_seeded_agent_ids_are_unique(self, db):
        from app.db.crud import get_all_agent_configs
        from app.db.seed import seed_all

        seed_all(db)

        configs = get_all_agent_configs(db)
        agent_ids = [c.agent_id for c in configs]

        assert len(agent_ids) == len(set(agent_ids)), (
            "Duplicate agent_ids found after seeding"
        )
