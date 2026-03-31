from __future__ import annotations

"""
core/agent_factory.py – Build CrewAI Agent instances from DB configuration.

Override hierarchy (highest → lowest priority):
    1. Per-agent LLM profile  (agent_configs.llm_profile_id)
    2. Run-level LLM profile  (passed in as `run_profile`)
    3. Global default profile (llm_profiles.is_default = True, queried from DB)
    4. ENV fallback           (settings.DEFAULT_LLM_*)

Usage:
    from app.core.agent_factory import AgentFactory

    factory = AgentFactory(db)
    agent = factory.build("requirement_analyzer")
    # or with a run-level override:
    agent = factory.build("requirement_analyzer", run_profile_id=3)
"""

import logging
from typing import Optional

from app.core.llm_factory import LLMFactory
from app.db.models import AgentConfig, LLMProfile
from crewai import Agent
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class AgentFactory:
    """
    Builds CrewAI Agent objects from AgentConfig rows stored in the database.

    The factory holds a DB session and an LLMFactory instance so both can be
    reused across multiple `build()` calls within the same request / task.
    """

    def __init__(
        self,
        db: Session,
        run_profile_id: Optional[int] = None,
    ) -> None:
        """
        Args:
            db:               Active SQLAlchemy session.
            run_profile_id:   Optional run-level LLM profile override.
                              When set, this profile is used for every agent
                              that does not have its own per-agent profile.
        """
        self._db = db
        self._llm_factory = LLMFactory(db)
        self._run_profile_id = run_profile_id

        # Lazy caches — populated on first use
        self._run_profile: Optional[LLMProfile] = None
        self._run_profile_loaded: bool = False
        self._agent_configs: dict[str, AgentConfig] = {}

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def build(
        self,
        agent_id: str,
        *,
        override_profile_id: Optional[int] = None,
    ) -> Agent:
        """
        Build a CrewAI Agent for the given agent_id.

        Args:
            agent_id:            Unique slug, e.g. "requirement_analyzer".
            override_profile_id: One-off LLM profile override (highest priority).
                                 Useful when you want to test a single agent with
                                 a different model without touching the DB.

        Returns:
            A fully-configured crewai.Agent instance.

        Raises:
            ValueError: If no AgentConfig row exists for the given agent_id.
        """
        config = self._get_config(agent_id)

        # Resolve the LLM following the override chain
        llm = self._resolve_llm(config, override_profile_id)

        agent_kwargs: dict = {
            "role": config.role,
            "goal": config.goal,
            "backstory": config.backstory,
            "verbose": config.verbose,
            "max_iter": config.max_iter,
            "allow_delegation": False,  # agents only do their own task
        }

        if llm is not None:
            agent_kwargs["llm"] = llm

        logger.debug(
            "Building agent %r (stage=%s, llm=%s)",
            agent_id,
            config.stage,
            getattr(llm, "model", "env-default"),
        )

        return Agent(**agent_kwargs)

    def build_many(
        self,
        agent_ids: list[str],
        *,
        enabled_only: bool = True,
    ) -> dict[str, Agent]:
        """
        Build multiple agents at once.

        Args:
            agent_ids:    List of agent_id slugs to build.
            enabled_only: If True, silently skip disabled agents instead of
                          raising an error.

        Returns:
            Dict mapping agent_id → Agent for every agent that was built.
        """
        result: dict[str, Agent] = {}

        for agent_id in agent_ids:
            config = self._get_config(agent_id)

            if enabled_only and not config.enabled:
                logger.info("Skipping disabled agent: %r", agent_id)
                continue

            result[agent_id] = self.build(agent_id)

        return result

    def build_for_stage(self, stage: str) -> dict[str, Agent]:
        """
        Build all enabled agents belonging to a specific pipeline stage.

        Args:
            stage: One of "ingestion" | "testcase" | "execution" | "reporting".

        Returns:
            Ordered dict of agent_id → Agent, in DB insertion order (= seed order).
        """
        from sqlalchemy import select

        stmt = (
            select(AgentConfig)
            .where(AgentConfig.stage == stage)
            .where(AgentConfig.enabled.is_(True))
            .order_by(AgentConfig.id)
        )
        configs = list(self._db.scalars(stmt).all())

        # Populate the config cache so build() calls below use cached values
        for cfg in configs:
            self._agent_configs[cfg.agent_id] = cfg

        return {cfg.agent_id: self.build(cfg.agent_id) for cfg in configs}

    # ─────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _get_config(self, agent_id: str) -> AgentConfig:
        """
        Return the AgentConfig for agent_id, using an internal cache to avoid
        repeated DB round-trips within the same factory instance.

        Raises:
            ValueError: If no row exists for the given agent_id.
        """
        if agent_id not in self._agent_configs:
            from sqlalchemy import select

            stmt = select(AgentConfig).where(AgentConfig.agent_id == agent_id)
            config = self._db.scalar(stmt)

            if config is None:
                raise ValueError(
                    f"No AgentConfig found for agent_id={agent_id!r}. "
                    "Run the database seeder first: python -m app.db.seed"
                )

            self._agent_configs[agent_id] = config

        return self._agent_configs[agent_id]

    def _get_run_profile(self) -> Optional[LLMProfile]:
        """
        Lazy-load the run-level LLM profile (if a run_profile_id was supplied).
        Result is cached so the DB is only hit once per factory instance.
        """
        if not self._run_profile_loaded:
            self._run_profile_loaded = True
            if self._run_profile_id is not None:
                self._run_profile = self._db.get(LLMProfile, self._run_profile_id)
                if self._run_profile is None:
                    logger.warning(
                        "Run-level LLM profile id=%d not found; "
                        "falling back to global default.",
                        self._run_profile_id,
                    )
        return self._run_profile

    def _resolve_llm(
        self,
        config: AgentConfig,
        override_profile_id: Optional[int],
    ):
        """
        Walk the override chain and return the first LLM object that can be built:

        priority 1 – one-off override_profile_id (passed directly to build())
        priority 2 – per-agent llm_profile (config.llm_profile)
        priority 3 – run-level profile     (self._run_profile_id)
        priority 4 – global default profile (is_default=True)
        priority 5 – ENV fallback           (LLMFactory handles this automatically)

        Returns None only when LLMFactory itself returns None (i.e. no LLM can
        be resolved at all — CrewAI will then use its own default).
        """
        # 1. One-off override
        if override_profile_id is not None:
            profile = self._db.get(LLMProfile, override_profile_id)
            if profile is not None:
                logger.debug(
                    "Agent %r: using one-off override profile %r",
                    config.agent_id,
                    profile.name,
                )
                return self._llm_factory.build_from_profile(profile)
            logger.warning(
                "Agent %r: override profile id=%d not found; falling back.",
                config.agent_id,
                override_profile_id,
            )

        # 2. Per-agent profile
        if config.llm_profile is not None:
            logger.debug(
                "Agent %r: using per-agent profile %r",
                config.agent_id,
                config.llm_profile.name,
            )
            return self._llm_factory.build_from_profile(config.llm_profile)

        # 3. Run-level profile
        run_profile = self._get_run_profile()
        if run_profile is not None:
            logger.debug(
                "Agent %r: using run-level profile %r",
                config.agent_id,
                run_profile.name,
            )
            return self._llm_factory.build_from_profile(run_profile)

        # 4 + 5. Global default / ENV fallback — delegated entirely to LLMFactory
        logger.debug(
            "Agent %r: no profile override found; using global default / ENV fallback.",
            config.agent_id,
        )
        return self._llm_factory.build_default()


# ─────────────────────────────────────────────────────────────────────────────
# Convenience function (for use outside request context)
# ─────────────────────────────────────────────────────────────────────────────


def build_agent(
    db: Session,
    agent_id: str,
    *,
    run_profile_id: Optional[int] = None,
) -> Agent:
    """
    Module-level convenience wrapper around AgentFactory.

    Example:
        agent = build_agent(db, "requirement_analyzer")
        agent = build_agent(db, "test_runner", run_profile_id=2)
    """
    factory = AgentFactory(db, run_profile_id=run_profile_id)
    return factory.build(agent_id)
