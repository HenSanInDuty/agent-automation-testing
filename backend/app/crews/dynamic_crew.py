from __future__ import annotations

"""
crews/dynamic_crew.py – Generic CrewAI crew for custom/dynamic pipeline stages.

Used by PipelineRunnerV2 when a stage has crew_type="crewai_sequential" or
"crewai_hierarchical" and is not a builtin stage.
"""
import logging
from typing import Any, Optional

from app.crews.base_crew import BaseCrew, ProgressCallback
from app.db.models import AgentConfigDocument

logger = logging.getLogger(__name__)


class DynamicCrewAICrew(BaseCrew):
    """
    Generic CrewAI crew that builds agents dynamically from AgentConfigDocuments.

    Used for both custom stages AND the 3 builtin CrewAI stages (testcase, execution,
    reporting) when PipelineRunnerV2 dynamically loads stage configs.
    """

    def __init__(
        self,
        stage: str,
        agent_configs: list[AgentConfigDocument],
        run_id: str,
        run_profile_id: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
        mock_mode: Optional[bool] = None,
        process: str = "sequential",  # "sequential" | "hierarchical"
    ) -> None:
        super().__init__(
            run_id=run_id,
            run_profile_id=run_profile_id,
            progress_callback=progress_callback,
            mock_mode=mock_mode,
        )
        self.stage = stage
        self._agent_configs = agent_configs
        self._process = process
        self.agent_ids = [c.agent_id for c in agent_configs]

    def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Execute the crew synchronously (called via asyncio.to_thread in runner)."""
        if self._is_mock_mode():
            return self._mock_run(input_data)

        try:
            from crewai import Agent, Crew, Process, Task
        except ImportError:
            logger.warning("crewai not available, returning mock output")
            return self._mock_run(input_data)

        self._emit_stage_started(agent_count=len(self._agent_configs))

        # Build agents (typed as list[Any] to satisfy Crew's invariant list[BaseAgent] param)
        agents: list[Any] = []
        tasks: list[Any] = []

        for config in self._agent_configs:
            if not config.enabled:
                continue

            self._emit_agent_started(config.agent_id, config.display_name)

            agent = Agent(
                role=config.role,
                goal=config.goal,
                backstory=config.backstory,
                verbose=config.verbose,
                max_iter=config.max_iter,
                allow_delegation=False,
            )
            agents.append(agent)

            task = Task(
                description=(
                    f"Process the following input for stage '{self.stage}': "
                    f"{str(input_data)[:1000]}"
                ),
                expected_output="JSON dict with stage results",
                agent=agent,
            )
            tasks.append(task)

        if not agents:
            logger.warning("[DynamicCrew] No enabled agents for stage=%r", self.stage)
            return {
                "stage": self.stage,
                "output": "No enabled agents",
                "input": input_data,
            }

        process = (
            Process.sequential
            if self._process == "sequential"
            else Process.hierarchical
        )
        crew = Crew(agents=agents, tasks=tasks, process=process, verbose=False)

        try:
            result = crew.kickoff()
            parsed = self._parse_json_output(result)

            for config in self._agent_configs:
                if config.enabled:
                    self._emit_agent_completed(config.agent_id, str(parsed)[:200])

            self._emit_stage_completed()
            return parsed if isinstance(parsed, dict) else {"output": parsed}

        except Exception as exc:
            logger.exception("[DynamicCrew] stage=%r failed: %s", self.stage, exc)
            for config in self._agent_configs:
                if config.enabled:
                    self._emit_agent_failed(config.agent_id, str(exc))
            raise

    def _mock_run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Return mock output for development/testing."""
        self._emit_stage_started(agent_count=len(self._agent_configs))
        for config in self._agent_configs:
            if config.enabled:
                self._emit_agent_started(config.agent_id, config.display_name)
                self._emit_agent_completed(
                    config.agent_id, f"[MOCK] {config.display_name} output"
                )
        self._emit_stage_completed()
        return {
            "stage": self.stage,
            "mock": True,
            "agent_count": len(self._agent_configs),
            "input_keys": list(input_data.keys()),
        }
