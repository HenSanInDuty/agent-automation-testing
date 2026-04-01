"""
tests/test_seed.py
──────────────────
Verify that seed_all() correctly inserts the default LLM profile and all
19 agent configs into an in-memory SQLite database.

Run with:
    cd backend
    uv run pytest tests/test_seed.py -v
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.database import Base
from app.db.models import AgentConfig, LLMProfile
from app.db.seed import (
    DEFAULT_AGENT_CONFIGS,
    DEFAULT_LLM_PROFILE,
    seed_agent_configs,
    seed_all,
    seed_llm_profiles,
)

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="function")
def db() -> Session:
    """
    Provide a fresh in-memory SQLite session for each test.
    Tables are created before the test and dropped after.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    # Import models so they register on Base.metadata
    from app.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestSession()

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


# ─────────────────────────────────────────────────────────────────────────────
# Default LLM Profile
# ─────────────────────────────────────────────────────────────────────────────


class TestSeedLLMProfiles:
    def test_inserts_default_profile(self, db: Session) -> None:
        seed_llm_profiles(db)

        profiles = db.query(LLMProfile).all()
        assert len(profiles) == 1

    def test_default_profile_name(self, db: Session) -> None:
        seed_llm_profiles(db)

        profile = db.query(LLMProfile).first()
        assert profile is not None
        assert profile.name == DEFAULT_LLM_PROFILE["name"]

    def test_default_profile_provider(self, db: Session) -> None:
        seed_llm_profiles(db)

        profile = db.query(LLMProfile).first()
        assert profile.provider == DEFAULT_LLM_PROFILE["provider"]

    def test_default_profile_model(self, db: Session) -> None:
        seed_llm_profiles(db)

        profile = db.query(LLMProfile).first()
        assert profile.model == DEFAULT_LLM_PROFILE["model"]

    def test_default_profile_is_default_flag(self, db: Session) -> None:
        seed_llm_profiles(db)

        profile = db.query(LLMProfile).first()
        assert profile.is_default is True

    def test_default_profile_temperature(self, db: Session) -> None:
        seed_llm_profiles(db)

        profile = db.query(LLMProfile).first()
        assert profile.temperature == DEFAULT_LLM_PROFILE["temperature"]

    def test_default_profile_max_tokens(self, db: Session) -> None:
        seed_llm_profiles(db)

        profile = db.query(LLMProfile).first()
        assert profile.max_tokens == DEFAULT_LLM_PROFILE["max_tokens"]

    def test_seed_is_idempotent(self, db: Session) -> None:
        """Calling seed_llm_profiles twice must not create duplicate rows."""
        seed_llm_profiles(db)
        seed_llm_profiles(db)

        profiles = db.query(LLMProfile).all()
        assert len(profiles) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Agent Configs – counts
# ─────────────────────────────────────────────────────────────────────────────


class TestSeedAgentConfigsCounts:
    def test_total_agent_count(self, db: Session) -> None:
        seed_agent_configs(db)

        total = db.query(AgentConfig).count()
        assert total == 19

    def test_total_matches_seed_data_length(self, db: Session) -> None:
        seed_agent_configs(db)

        total = db.query(AgentConfig).count()
        assert total == len(DEFAULT_AGENT_CONFIGS)

    def test_testcase_stage_count(self, db: Session) -> None:
        seed_agent_configs(db)

        count = db.query(AgentConfig).filter(AgentConfig.stage == "testcase").count()
        assert count == 10

    def test_execution_stage_count(self, db: Session) -> None:
        seed_agent_configs(db)

        count = db.query(AgentConfig).filter(AgentConfig.stage == "execution").count()
        assert count == 5

    def test_ingestion_stage_count(self, db: Session) -> None:
        seed_agent_configs(db)

        count = db.query(AgentConfig).filter(AgentConfig.stage == "ingestion").count()
        assert count == 1

    def test_reporting_stage_count(self, db: Session) -> None:
        seed_agent_configs(db)

        count = db.query(AgentConfig).filter(AgentConfig.stage == "reporting").count()
        assert count == 3

    def test_seed_agents_is_idempotent(self, db: Session) -> None:
        """Calling seed_agent_configs twice must not create duplicate rows."""
        seed_agent_configs(db)
        seed_agent_configs(db)

        total = db.query(AgentConfig).count()
        assert total == 19


# ─────────────────────────────────────────────────────────────────────────────
# Agent Configs – all expected agent_ids are present
# ─────────────────────────────────────────────────────────────────────────────

EXPECTED_AGENT_IDS = [
    # ingestion (1)
    "ingestion_pipeline",
    # testcase (10)
    "requirement_analyzer",
    "rule_parser",
    "scope_classifier",
    "data_model_agent",
    "test_condition_agent",
    "dependency_agent",
    "test_case_generator",
    "automation_agent",
    "coverage_agent_pre",
    "report_agent_pre",
    # execution (5)
    "execution_orchestrator",
    "env_adapter",
    "test_runner",
    "execution_logger",
    "result_store",
    # reporting (3)
    "coverage_analyzer",
    "root_cause_analyzer",
    "report_generator",
]


class TestSeedAgentConfigsIds:
    def test_all_agent_ids_present(self, db: Session) -> None:
        seed_agent_configs(db)

        stored_ids = {row[0] for row in db.query(AgentConfig.agent_id).all()}
        for agent_id in EXPECTED_AGENT_IDS:
            assert agent_id in stored_ids, f"Missing agent: {agent_id!r}"

    def test_no_extra_agent_ids(self, db: Session) -> None:
        seed_agent_configs(db)

        stored_ids = {row[0] for row in db.query(AgentConfig.agent_id).all()}
        expected_set = set(EXPECTED_AGENT_IDS)
        extra = stored_ids - expected_set
        assert not extra, f"Unexpected extra agents seeded: {extra}"

    def test_agent_ids_are_unique(self, db: Session) -> None:
        seed_agent_configs(db)

        all_ids = [row[0] for row in db.query(AgentConfig.agent_id).all()]
        assert len(all_ids) == len(set(all_ids)), "Duplicate agent_ids detected"


# ─────────────────────────────────────────────────────────────────────────────
# Agent Configs – field quality checks
# ─────────────────────────────────────────────────────────────────────────────


class TestSeedAgentConfigsFields:
    def test_all_agents_have_non_empty_role(self, db: Session) -> None:
        seed_agent_configs(db)

        agents = db.query(AgentConfig).all()
        for agent in agents:
            assert agent.role and agent.role.strip(), (
                f"Agent {agent.agent_id!r} has empty role"
            )

    def test_all_agents_have_non_empty_goal(self, db: Session) -> None:
        seed_agent_configs(db)

        agents = db.query(AgentConfig).all()
        for agent in agents:
            assert agent.goal and agent.goal.strip(), (
                f"Agent {agent.agent_id!r} has empty goal"
            )

    def test_all_agents_have_non_empty_backstory(self, db: Session) -> None:
        seed_agent_configs(db)

        agents = db.query(AgentConfig).all()
        for agent in agents:
            assert agent.backstory and agent.backstory.strip(), (
                f"Agent {agent.agent_id!r} has empty backstory"
            )

    def test_all_agents_have_non_empty_display_name(self, db: Session) -> None:
        seed_agent_configs(db)

        agents = db.query(AgentConfig).all()
        for agent in agents:
            assert agent.display_name and agent.display_name.strip(), (
                f"Agent {agent.agent_id!r} has empty display_name"
            )

    def test_all_agents_enabled_by_default(self, db: Session) -> None:
        seed_agent_configs(db)

        agents = db.query(AgentConfig).all()
        for agent in agents:
            assert agent.enabled is True, (
                f"Agent {agent.agent_id!r} should be enabled by default"
            )

    def test_all_agents_verbose_false_by_default(self, db: Session) -> None:
        seed_agent_configs(db)

        agents = db.query(AgentConfig).all()
        for agent in agents:
            assert agent.verbose is False, (
                f"Agent {agent.agent_id!r} should have verbose=False by default"
            )

    def test_all_agents_have_valid_max_iter(self, db: Session) -> None:
        seed_agent_configs(db)

        agents = db.query(AgentConfig).all()
        for agent in agents:
            assert 1 <= agent.max_iter <= 50, (
                f"Agent {agent.agent_id!r} max_iter={agent.max_iter} is out of range"
            )

    def test_all_agents_have_valid_stage(self, db: Session) -> None:
        valid_stages = {"ingestion", "testcase", "execution", "reporting"}
        seed_agent_configs(db)

        agents = db.query(AgentConfig).all()
        for agent in agents:
            assert agent.stage in valid_stages, (
                f"Agent {agent.agent_id!r} has invalid stage {agent.stage!r}"
            )

    def test_no_agent_has_llm_profile_override_by_default(self, db: Session) -> None:
        """Fresh agents must not point to any LLM profile — they use the global default."""
        seed_agent_configs(db)

        agents = db.query(AgentConfig).all()
        for agent in agents:
            assert agent.llm_profile_id is None, (
                f"Agent {agent.agent_id!r} should have llm_profile_id=None by default"
            )

    def test_all_agents_have_created_at(self, db: Session) -> None:
        seed_agent_configs(db)

        agents = db.query(AgentConfig).all()
        for agent in agents:
            assert agent.created_at is not None, (
                f"Agent {agent.agent_id!r} has no created_at"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Individual agent spot-checks
# ─────────────────────────────────────────────────────────────────────────────


class TestSeedAgentSpotChecks:
    def test_requirement_analyzer_stage(self, db: Session) -> None:
        seed_agent_configs(db)

        agent = db.query(AgentConfig).filter_by(agent_id="requirement_analyzer").first()
        assert agent is not None
        assert agent.stage == "testcase"

    def test_test_runner_stage(self, db: Session) -> None:
        seed_agent_configs(db)

        agent = db.query(AgentConfig).filter_by(agent_id="test_runner").first()
        assert agent is not None
        assert agent.stage == "execution"

    def test_report_generator_stage(self, db: Session) -> None:
        seed_agent_configs(db)

        agent = db.query(AgentConfig).filter_by(agent_id="report_generator").first()
        assert agent is not None
        assert agent.stage == "reporting"

    def test_test_runner_has_higher_max_iter(self, db: Session) -> None:
        """test_runner handles real HTTP calls — it's given more iterations."""
        seed_agent_configs(db)

        runner = db.query(AgentConfig).filter_by(agent_id="test_runner").first()
        assert runner is not None
        assert runner.max_iter >= 5

    def test_result_store_has_low_max_iter(self, db: Session) -> None:
        """result_store is a persistence agent — it needs fewer iterations."""
        seed_agent_configs(db)

        store = db.query(AgentConfig).filter_by(agent_id="result_store").first()
        assert store is not None
        assert store.max_iter <= 5


# ─────────────────────────────────────────────────────────────────────────────
# seed_all() — combined run
# ─────────────────────────────────────────────────────────────────────────────


class TestSeedAll:
    def test_seed_all_creates_profile_and_agents(self, db: Session) -> None:
        seed_all(db)

        profiles = db.query(LLMProfile).all()
        agents = db.query(AgentConfig).all()

        assert len(profiles) == 1
        assert len(agents) == 19

    def test_seed_all_is_idempotent(self, db: Session) -> None:
        seed_all(db)
        seed_all(db)
        seed_all(db)

        profiles = db.query(LLMProfile).all()
        agents = db.query(AgentConfig).all()

        assert len(profiles) == 1
        assert len(agents) == 19

    def test_seed_all_preserves_user_customisations(self, db: Session) -> None:
        """
        If an admin has modified an agent's role, re-seeding must NOT overwrite it.
        """
        seed_all(db)

        # Simulate an admin edit
        agent = db.query(AgentConfig).filter_by(agent_id="requirement_analyzer").first()
        assert agent is not None
        agent.role = "Custom Role Overridden By Admin"
        db.commit()

        # Re-seed
        seed_all(db)

        # Verify the custom role was preserved
        agent = db.query(AgentConfig).filter_by(agent_id="requirement_analyzer").first()
        assert agent is not None
        assert agent.role == "Custom Role Overridden By Admin"
