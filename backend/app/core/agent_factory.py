"""
core/agent_factory.py – Build CrewAI Agent instances from DB configuration.

Override hierarchy (highest → lowest priority):
    1. Per-agent LLM profile  (AgentConfigDocument.llm_profile_id)
    2. Run-level LLM profile  (passed in as ``run_profile_id``)
    3. Global default profile (LLMProfileDocument.is_default = True)
    4. ENV fallback           (settings.DEFAULT_LLM_*)

All public methods are ``async`` because they may need to hit MongoDB to load
agent configs or LLM profiles on first use.

Usage::

    factory = AgentFactory(run_profile_id="64f1a2b3c4d5e6f7a8b9c0d1")
    agent = await factory.build("requirement_analyzer")

    # Build all enabled agents for a stage at once:
    agents = await factory.build_for_stage("testcase")
"""

from __future__ import annotations

import logging
from typing import Optional

try:
    from crewai import Agent  # type: ignore[import-untyped]
except ImportError:
    Agent = None  # type: ignore[assignment,misc]

from app.core.llm_factory import LLMFactory
from app.db.models import AgentConfigDocument

logger = logging.getLogger(__name__)


class AgentFactory:
    """Async factory that builds CrewAI ``Agent`` objects from MongoDB config.

    The factory holds an :class:`~app.core.llm_factory.LLMFactory` instance
    so both the config cache and the LLM cache can be reused across multiple
    :meth:`build` calls within the same pipeline run.

    Args:
        run_profile_id: Optional MongoDB ObjectId string of the run-level LLM
            profile override.  When set, every agent that has no per-agent
            profile uses this profile instead of the global default.
    """

    def __init__(
        self,
        run_profile_id: Optional[str] = None,
    ) -> None:
        self._run_profile_id = run_profile_id
        self._llm_factory = LLMFactory(run_profile_id=run_profile_id)

        # Lazy caches — populated on first use to avoid unnecessary DB round-trips
        self._agent_configs: dict[str, AgentConfigDocument] = {}

        logger.debug(
            "[AgentFactory] Initialised  run_profile_id=%s",
            run_profile_id,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    async def build(
        self,
        agent_id: str,
        *,
        override_profile_id: Optional[str] = None,
    ) -> "Agent":  # type: ignore[name-defined]  # crewai imported lazily
        """Build a CrewAI ``Agent`` for the given *agent_id*.

        The LLM override chain is resolved in this order:

        1. *override_profile_id* argument (one-off, highest priority).
        2. Per-agent ``llm_profile_id`` stored in
           :class:`~app.db.models.AgentConfigDocument`.
        3. Run-level ``run_profile_id`` supplied to the constructor.
        4. Global default profile (``is_default=True``).
        5. ENV-variable fallback handled by
           :class:`~app.core.llm_factory.LLMFactory`.

        Args:
            agent_id:            Unique slug, e.g. ``"requirement_analyzer"``.
            override_profile_id: One-off LLM profile ObjectId string (highest
                                 priority override for this single call).

        Returns:
            A fully-configured :class:`crewai.Agent` instance.

        Raises:
            ValueError: If no :class:`~app.db.models.AgentConfigDocument` row
                exists for the given *agent_id*.
        """
        # Use module-level Agent (imported at top with try/except fallback)

        config = await self._get_config(agent_id)

        # Resolve the LLM following the override chain
        llm = await self._resolve_llm(config, override_profile_id)

        agent_kwargs: dict = {
            "role": config.role,
            "goal": config.goal,
            "backstory": config.backstory,
            "verbose": config.verbose,
            "max_iter": config.max_iter,
            "allow_delegation": False,  # agents only execute their own task
        }

        if llm is not None:
            agent_kwargs["llm"] = llm

        # Resolve tools from ToolRegistry using the agent's configured tool_names
        if config.tool_names:
            from app.tools.registry import ToolRegistry  # noqa: PLC0415
            tools = ToolRegistry.resolve(config.tool_names)
            if tools:
                agent_kwargs["tools"] = tools
                logger.debug(
                    "[AgentFactory] Attached %d tool(s) to agent %r: %s",
                    len(tools),
                    agent_id,
                    config.tool_names,
                )

        logger.debug(
            "[AgentFactory] Built agent %r  stage=%s  llm=%s  tools=%s",
            agent_id,
            config.stage,
            getattr(llm, "model", "env-default"),
            config.tool_names or [],
        )

        return Agent(**agent_kwargs)

    async def build_many(
        self,
        agent_ids: list[str],
        *,
        enabled_only: bool = True,
    ) -> dict[str, "Agent"]:  # type: ignore[name-defined]
        """Build multiple agents at once.

        Args:
            agent_ids:    List of agent_id slugs to build.
            enabled_only: When ``True``, silently skip disabled agents instead
                          of raising a :class:`ValueError`.

        Returns:
            Mapping of ``agent_id`` → :class:`crewai.Agent` for every agent
            that was successfully built.
        """
        result: dict[str, "Agent"] = {}  # type: ignore[name-defined]

        for agent_id in agent_ids:
            config = await self._get_config(agent_id)

            if enabled_only and not config.enabled:
                logger.info("[AgentFactory] Skipping disabled agent: %r", agent_id)
                continue

            result[agent_id] = await self.build(agent_id)

        return result

    async def build_for_stage(self, stage: str) -> dict[str, "Agent"]:  # type: ignore[name-defined]
        """Build all enabled agents belonging to a specific pipeline stage.

        Fetches the configs for *stage* from MongoDB, populates the internal
        cache, then calls :meth:`build` for each one.

        Args:
            stage: One of ``"ingestion"``, ``"testcase"``, ``"execution"``,
                   ``"reporting"``, or any custom stage slug.

        Returns:
            Ordered mapping of ``agent_id`` → :class:`crewai.Agent` in seed
            insertion order.
        """
        from app.db import crud

        configs = await crud.get_agent_configs_for_stage(stage, enabled_only=True)

        # Pre-populate the cache so build() calls below skip the DB lookup
        for cfg in configs:
            self._agent_configs[cfg.agent_id] = cfg

        return {cfg.agent_id: await self.build(cfg.agent_id) for cfg in configs}

    # ─────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────────

    async def _get_config(self, agent_id: str) -> AgentConfigDocument:
        """Return the :class:`~app.db.models.AgentConfigDocument` for *agent_id*.

        Results are cached per factory instance to avoid repeated DB hits
        within the same pipeline run.

        Args:
            agent_id: Unique agent slug.

        Returns:
            The matching document.

        Raises:
            ValueError: If no document exists for *agent_id*.
        """
        if agent_id not in self._agent_configs:
            from app.db import crud

            config = await crud.get_agent_config(agent_id)

            if config is None:
                raise ValueError(
                    f"No AgentConfig found for agent_id={agent_id!r}. "
                    "Run the database seeder first: python -m app.db.seed"
                )

            self._agent_configs[agent_id] = config

        return self._agent_configs[agent_id]

    async def _resolve_llm(
        self,
        config: AgentConfigDocument,
        override_profile_id: Optional[str],
    ):
        """Walk the LLM override chain and return the first resolved LLM object.

        Resolution order:

        1. *override_profile_id* argument → one-off override.
        2. ``config.llm_profile_id`` → per-agent profile.
        3. Run-level ``_run_profile_id`` → set on the factory constructor.
        4. Global default / ENV fallback → delegated to
           :class:`~app.core.llm_factory.LLMFactory`.

        Args:
            config:              Agent config document being built.
            override_profile_id: Optional one-off profile ObjectId string.

        Returns:
            A CrewAI ``LLM`` object, or ``None`` if no profile could be
            resolved (CrewAI will then use its own built-in default).
        """
        from app.db import crud

        # 1. One-off override (highest priority)
        if override_profile_id is not None:
            profile = await crud.get_llm_profile(override_profile_id)
            if profile is not None:
                logger.debug(
                    "[AgentFactory] Agent %r: using one-off override profile %r",
                    config.agent_id,
                    profile.name,
                )
                return self._llm_factory.build_from_profile(profile)
            logger.warning(
                "[AgentFactory] Agent %r: override profile id=%r not found; "
                "falling back.",
                config.agent_id,
                override_profile_id,
            )

        # 2. Per-agent profile
        if config.llm_profile_id is not None:
            profile = await crud.get_llm_profile(config.llm_profile_id)
            if profile is not None:
                logger.debug(
                    "[AgentFactory] Agent %r: using per-agent profile %r",
                    config.agent_id,
                    profile.name,
                )
                return self._llm_factory.build_from_profile(profile)

        # 3 + 4. Run-level / global default / ENV fallback
        logger.debug(
            "[AgentFactory] Agent %r: no direct profile; "
            "delegating to LLMFactory (run_profile_id=%s).",
            config.agent_id,
            self._run_profile_id,
        )
        return await self._llm_factory.build_default()


# ─────────────────────────────────────────────────────────────────────────────
# Convenience function (for use outside request context)
# ─────────────────────────────────────────────────────────────────────────────


async def build_agent(
    agent_id: str,
    *,
    run_profile_id: Optional[str] = None,
) -> "Agent":  # type: ignore[name-defined]
    """Async module-level convenience wrapper around :class:`AgentFactory`.

    Args:
        agent_id:        Unique agent slug to build.
        run_profile_id:  Optional MongoDB ObjectId string of the run-level
                         LLM profile override.

    Returns:
        A fully-configured :class:`crewai.Agent` instance.

    Example::

        agent = await build_agent("requirement_analyzer")
        agent = await build_agent("test_runner", run_profile_id="64f1a2b3...")
    """
    factory = AgentFactory(run_profile_id=run_profile_id)
    return await factory.build(agent_id)
