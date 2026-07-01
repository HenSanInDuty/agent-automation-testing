"""
crews/request_body_synthesizer_crew.py
──────────────────────────────────────
Optional LLM refinement layer for happy-path request bodies.

The deterministic resolver (:func:`app.tools.request_body_synthesizer.
resolve_request_body`) already turns schema-placeholder examples
(``{"date": "YYYY-MM-DD", "title": "string"}``) into valid, bindable values.
This crew goes one step further: it asks a single agent to read each
body-carrying endpoint's field rules + example and return **domain-realistic**
values (a real-looking title, a date that respects "future date" rules, …),
keyed by ``"<METHOD> <path>"``.

It is **advisory and best-effort**: on mock mode, no body endpoints, an LLM
failure, or unparseable output, :meth:`synthesize` returns ``{}`` and the
caller keeps the deterministic bodies. The baseline is never blocked.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from app.crews.base_crew import BaseCrew, ProgressCallback
from app.tools.md_api_spec_validator import ParsedEndpointSpec, ParsedSpec
from app.tools.request_body_synthesizer import resolve_request_body

logger = logging.getLogger(__name__)

# Seeded AgentConfig.agent_id for this crew.
BODY_SYNTHESIZER_AGENT_ID = "request_body_synthesizer"

# Methods that carry a request body.
_METHODS_WITH_BODY = {"POST", "PUT", "PATCH"}

_OUTPUT_CONTRACT = (
    "Return ONLY a JSON object mapping each target key (exactly as given, e.g. "
    '"POST /api/tasks") to an object of field→value pairs forming ONE valid, '
    "domain-realistic request body. Keep every field present in the reference "
    "body, honour the declared type and rules, and use believable values "
    "(a real-looking title, an in-range date/time, a valid email). Emit no "
    "prose, no markdown fences, and never invent fields not in the schema."
)


class RequestBodySynthesizerCrew(BaseCrew):
    """Refine happy-path request bodies with one best-effort LLM call."""

    stage = "testcase"
    agent_ids: list[str] = [BODY_SYNTHESIZER_AGENT_ID]

    def __init__(
        self,
        run_id: str,
        run_profile_id: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
        mock_mode: Optional[bool] = None,
        **_kwargs: Any,
    ) -> None:
        super().__init__(
            run_id=run_id,
            run_profile_id=run_profile_id,
            progress_callback=progress_callback,
            mock_mode=mock_mode,
        )

    # ── Required by BaseCrew (not the primary entry point) ────────────────────

    def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Adapter for the BaseCrew contract; callers use :meth:`synthesize`."""
        parsed = ParsedSpec.model_validate(input_data.get("md_spec_parsed") or {})
        return {"body_seeds": self.synthesize(parsed)}

    # ── Primary entry point ───────────────────────────────────────────────────

    def synthesize(self, parsed: ParsedSpec) -> dict[str, dict[str, Any]]:
        """Return LLM-refined bodies keyed by ``"<METHOD> <path>"`` (``{}`` on fail)."""
        targets = self._targets(parsed)
        if not targets or self._is_mock_mode():
            return {}

        self._emit_agent_started(BODY_SYNTHESIZER_AGENT_ID, "Request Body Synthesizer")
        try:
            raw = self._run_async_from_thread(
                self._invoke(targets), timeout=120.0
            )
            seeds = self._map(raw, targets)
        except Exception as exc:  # noqa: BLE001 — documented fallback, no retry
            logger.warning(
                "[BodySynthesizer][%s] synthesis failed: %s", self._run_id, exc
            )
            self._emit_log(
                f"Request body synthesizer unavailable ({exc}); using "
                "deterministic bodies.",
                level="warning",
            )
            self._emit_agent_completed(
                BODY_SYNTHESIZER_AGENT_ID, output_preview="fallback (deterministic)"
            )
            return {}

        self._emit_agent_completed(
            BODY_SYNTHESIZER_AGENT_ID,
            output_preview=f"{len(seeds)} body(ies) refined",
        )
        return seeds

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _targets(parsed: ParsedSpec) -> dict[str, ParsedEndpointSpec]:
        """Collect body-carrying endpoints keyed by ``"<METHOD> <path>"``."""
        targets: dict[str, ParsedEndpointSpec] = {}
        for ep in parsed.endpoints:
            method = (ep.endpoint.method or "").upper()
            if method not in _METHODS_WITH_BODY:
                continue
            if not (ep.request.body_fields or ep.request.raw_body_schema):
                continue
            targets[f"{method} {ep.endpoint.path}"] = ep
        return targets

    async def _invoke(self, targets: dict[str, ParsedEndpointSpec]) -> Any:
        from crewai import Crew, Process, Task  # type: ignore[import-untyped]

        from app.core.agent_factory import AgentFactory

        factory = AgentFactory(run_profile_id=self._run_profile_id)
        agent = await factory.build(BODY_SYNTHESIZER_AGENT_ID)
        description, expected_output = self._build_prompt(targets)
        task = Task(description=description, expected_output=expected_output, agent=agent)
        crew = Crew(
            agents=[agent], tasks=[task], process=Process.sequential, verbose=False
        )
        import asyncio

        return await asyncio.to_thread(crew.kickoff)

    @staticmethod
    def _build_prompt(targets: dict[str, ParsedEndpointSpec]) -> tuple[str, str]:
        """Render a prompt describing each target's schema + deterministic body."""
        digest = []
        for key, ep in targets.items():
            digest.append(
                {
                    "key": key,
                    "fields": [
                        {
                            "name": f.name,
                            "type": f.type,
                            "required": f.required,
                            "rules": f.rules,
                        }
                        for f in ep.request.body_fields
                    ],
                    "example": ep.request.raw_body_schema,
                    "reference_body": resolve_request_body(ep.request),
                }
            )
        description = "\n".join(
            [
                "You synthesize realistic, valid happy-path request bodies for "
                "API tests. For each target below you are given its declared "
                "fields/rules, the spec example, and a deterministic "
                "reference_body that is already valid but generic. Improve each "
                "reference_body into a domain-realistic body that still satisfies "
                "every type and rule.",
                "",
                "TARGETS:",
                json.dumps(digest, ensure_ascii=False, default=str),
                "",
                _OUTPUT_CONTRACT,
            ]
        )
        expected_output = (
            'A JSON object mapping each target key to a body object, e.g. '
            '{"POST /api/tasks": {"title": "Team standup", "date": "2026-06-30"}}. '
            "No prose, no markdown."
        )
        return description, expected_output

    def _map(
        self, raw: Any, targets: dict[str, ParsedEndpointSpec]
    ) -> dict[str, dict[str, Any]]:
        """Map raw agent JSON → ``{key: body}``, keeping only valid dict bodies."""
        parsed = self._parse_json_output(raw)
        if not isinstance(parsed, dict) or "raw_output" in parsed:
            raise ValueError("body synthesizer returned non-JSON output")

        seeds: dict[str, dict[str, Any]] = {}
        for key, body in parsed.items():
            if key in targets and isinstance(body, dict) and body:
                seeds[key] = body
        return seeds
