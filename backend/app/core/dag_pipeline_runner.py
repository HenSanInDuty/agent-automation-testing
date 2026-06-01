"""
core/dag_pipeline_runner.py – V3 DAG-based pipeline execution engine.

Executes a PipelineTemplateDocument as a directed-acyclic graph (DAG).
Nodes in the same execution layer run in parallel via asyncio.gather.
Pause/Resume/Cancel signals are checked between layers.
Failed nodes are retried up to node_config.retry_count times.

Usage::

    runner = DAGPipelineRunner(
        run_id="abc-123",
        template=template_doc,
        llm_profile_id=None,
        progress_callback=ws_broadcaster,
        mock_mode=False,
    )
    result = await runner.run({"file_path": "/uploads/spec.pdf", "document_name": "spec.pdf"})
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from app.core.dag_resolver import DAGResolver, DAGValidationError
from app.core.errors import StructuredPipelineError, is_structured_pipeline_error
from app.core.signal_manager import PipelineSignal, signal_manager
from app.db import crud
from app.db.models import NodeType, PipelineNodeConfig, PipelineTemplateDocument

logger = logging.getLogger(__name__)

# Playwright agent IDs that may generate file artifacts
_PLAYWRIGHT_AGENT_IDS = frozenset({"playwright_spec_writer", "playwright_fixture_writer"})

# Keys stripped from upstream input before carrying it forward in a node's
# output. `document_content` is re-injected per-agent by the runner from
# `self._document_content`; `_html_bytes` / `_docx_bytes` are short-lived
# bytes that only flow from ExportCrew to ReportVerifierCrew (single hop)
# and must never be persisted in PipelineResultDocument; `__sources__` is a
# multi-parent merge marker that should not accumulate across hops.
_NON_PROPAGATING_KEYS = frozenset({
    "document_content",
    "__sources__",
    "_html_bytes",
    "_docx_bytes",
})

# Keys whose value must be a list of dicts in the canonical pipeline schema.
# When a downstream LLM agent hallucinates a value here (e.g. emits
# ``test_cases: ["TC-1", "TC-2"]`` or an empty list), the carry-forward keeps
# the upstream list of dicts instead of letting the bad value poison the
# report verifier (which calls ``.get(...)`` on each element).
_STRUCTURED_LIST_KEYS = frozenset({
    "test_cases",
    "results",
    "unit_test_files",
})

# Callback type: (event_type: str, data: dict) -> None
ProgressCallback = Callable[[str, dict[str, Any]], None]


def _is_list_of_dicts(value: Any) -> bool:
    """True if *value* is a non-empty list whose every item is a dict."""
    return (
        isinstance(value, list)
        and len(value) > 0
        and all(isinstance(item, dict) for item in value)
    )


def _carry_forward(
    merged_input: dict[str, Any],
    node_output: Any,
) -> Any:
    """Carry upstream structured data forward into a node's output.

    Without this, agent nodes (which return only the LLM's JSON) and a few
    pure-python crews (Ingestion, Artifact, MDSpecVerifier) drop upstream
    keys like ``test_cases`` / ``results`` / ``unit_test_files``, leaving
    the final ``report_verifier`` with empty components.

    The merge gives precedence to ``node_output`` — a node may still
    override any inherited key — while excluding bytes/blobs listed in
    ``_NON_PROPAGATING_KEYS``.

    For ``_STRUCTURED_LIST_KEYS`` the carry is stricter: if upstream already
    holds a non-empty list of dicts and the downstream value is missing,
    empty, or doesn't carry the same shape (e.g. an LLM hallucinated a list
    of strings or scalars), the upstream list wins. This prevents the
    report-verifier from receiving lists whose elements lack ``.get()``.
    """
    if not isinstance(node_output, dict):
        return node_output
    if not isinstance(merged_input, dict) or not merged_input:
        return node_output
    carried = {
        k: v
        for k, v in merged_input.items()
        if k not in _NON_PROPAGATING_KEYS
    }
    merged = {**carried, **node_output}
    for k in _STRUCTURED_LIST_KEYS:
        if k in carried and _is_list_of_dicts(carried[k]):
            if not _is_list_of_dicts(merged.get(k)):
                merged[k] = carried[k]
    return merged


class DAGPipelineRunner:
    """
    DAG-based pipeline executor.

    Reads a PipelineTemplateDocument, resolves execution layers via DAGResolver,
    and runs each layer's nodes concurrently with asyncio.gather.
    Signals (pause/resume/cancel) are checked between layers.
    Retry logic uses exponential back-off per node_config.retry_count.

    Args:
        run_id:            UUID string of the PipelineRunDocument.
        template:          The resolved PipelineTemplateDocument.
        llm_profile_id:    Optional ObjectId string to override the LLM profile.
        progress_callback: Sync callable ``(event_type, data_dict) → None``.
                           Called from the async event loop; use
                           ``manager.broadcast_from_thread`` if you need
                           cross-thread broadcasting.
        mock_mode:         When True, skip real LLM calls (for testing).
    """

    def __init__(
        self,
        run_id: str,
        template: PipelineTemplateDocument,
        llm_profile_id: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
        mock_mode: bool = False,
        parent_run_id: Optional[str] = None,
        rerun_from_node: Optional[str] = None,
        node_llm_overrides: Optional[dict[str, str]] = None,
    ) -> None:
        self._run_id = run_id
        self._template = template
        self._llm_profile_id = llm_profile_id
        self._progress_callback = progress_callback
        self._mock_mode = mock_mode

        # Derived-run parameters
        self._parent_run_id = parent_run_id
        self._rerun_from_node = rerun_from_node
        self._node_llm_overrides: dict[str, str] = node_llm_overrides or {}

        # Node outputs cache: { node_id: output_dict }
        self._node_outputs: dict[str, dict] = {}  # type: ignore[type-arg]

        # Set of node_ids whose outputs were loaded from the parent run
        # (will be skipped during execution).
        self._inherited_nodes: set[str] = set()

        # Original document content — injected into every agent's merged_input
        # so all nodes in the DAG have access regardless of their depth.
        self._document_content: str = ""

        # Document name — forwarded to Kafka pipeline_events for correlation.
        self._document_name: str = ""

        # DAG resolver
        self._resolver = DAGResolver(template.nodes, template.edges)

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    async def run(self, initial_input: dict) -> dict:  # type: ignore[type-arg]
        """
        Execute the full pipeline DAG.

        Args:
            initial_input: Seed data for the INPUT node
                           (e.g. {"file_path": "...", "document_name": "..."}).

        Returns:
            Final output dict from the OUTPUT node.

        Raises:
            DAGValidationError: If the DAG is structurally invalid.
            Exception:          Re-raises any node execution failure after
                                exhausting retries (also marks run as failed).
        """
        start_time = time.time()

        # ── 1. Validate DAG ──────────────────────────────────────────────────
        try:
            self._resolver.validate()
        except DAGValidationError as exc:
            await crud.update_pipeline_run(
                self._run_id, status="failed", error_message=str(exc)
            )
            self._emit("run.failed", {"error": str(exc)})
            raise

        # ── 2. Compute execution layers ──────────────────────────────────────
        layers = self._resolver.get_execution_layers()
        await crud.update_pipeline_run(
            self._run_id,
            status="running",
            execution_layers=layers,
            started_at=datetime.now(timezone.utc),
        )
        self._emit(
            "run.started",
            {
                "template_id": self._template.template_id,
                "total_layers": len(layers),
                "total_nodes": sum(len(layer) for layer in layers),
                "layers": layers,
            },
        )

        # ── 3. Seed INPUT node output ────────────────────────────────────────
        input_node = next(
            n for n in self._template.nodes if n.node_type == NodeType.INPUT
        )
        self._node_outputs[input_node.node_id] = initial_input
        self._document_content = initial_input.get("document_content") or ""
        self._document_name = initial_input.get("document_name") or ""

        # ── 3b. Load inherited node outputs from parent run ──────────────────
        if self._parent_run_id and self._rerun_from_node:
            await self._load_inherited_nodes(layers)

        for layer_idx, layer_node_ids in enumerate(layers):
            # Skip layers that contain only the INPUT node (already seeded)
            if all(
                self._get_node(nid).node_type == NodeType.INPUT
                for nid in layer_node_ids
            ):
                continue

            # ── Check signals before the layer ──────────────────────────────
            signal = await signal_manager.get_signal(self._run_id)

            if signal == PipelineSignal.CANCEL:
                await self._handle_cancel()
                return self._build_result()

            if signal == PipelineSignal.PAUSE:
                self._emit(
                    "run.paused",
                    {
                        "completed_layers": layer_idx,
                        "next_layer": layer_node_ids,
                    },
                )
                await crud.update_pipeline_run(
                    self._run_id,
                    status="paused",
                    paused_at=datetime.now(timezone.utc),
                )
                logger.info(
                    "[DAGRunner] Paused run_id=%r before layer %d",
                    self._run_id,
                    layer_idx,
                )
                # Block until resume or cancel
                resumed_signal = await signal_manager.wait_for_resume(self._run_id)
                if resumed_signal == PipelineSignal.CANCEL:
                    await self._handle_cancel()
                    return self._build_result()

                self._emit("run.resumed", {"continuing_from_layer": layer_idx})
                await crud.update_pipeline_run(
                    self._run_id,
                    status="running",
                    resumed_at=datetime.now(timezone.utc),
                )
                logger.info(
                    "[DAGRunner] Resumed run_id=%r at layer %d",
                    self._run_id,
                    layer_idx,
                )

            # ── Emit layer started ───────────────────────────────────────────
            layer_start = time.time()
            self._emit(
                "layer.started",
                {
                    "layer_index": layer_idx,
                    "nodes": layer_node_ids,
                    "parallel": len(layer_node_ids) > 1,
                },
            )

            # ── Build tasks for enabled nodes in this layer ──────────────────
            enabled_ids: list[str] = []
            tasks: list = []

            for node_id in layer_node_ids:
                node_config = self._get_node(node_id)
                if not node_config.enabled:
                    self._emit(
                        "node.skipped",
                        {"node_id": node_id, "reason": "node disabled"},
                    )
                    continue
                # Skip inherited nodes — their outputs are already loaded
                if node_id in self._inherited_nodes:
                    self._emit(
                        "node.skipped",
                        {"node_id": node_id, "reason": "inherited from parent run"},
                    )
                    await crud.update_pipeline_run(
                        self._run_id,
                        completed_nodes=[*self._get_current_completed(), node_id],
                        node_statuses={node_id: "skipped"},
                    )
                    continue
                parent_outputs = self._gather_inputs(node_id)
                enabled_ids.append(node_id)
                tasks.append(self._execute_node_with_retry(node_config, parent_outputs))

            if not tasks:
                # All nodes in this layer were disabled — skip silently
                continue

            # ── Run all enabled nodes in this layer concurrently ─────────────
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # ── Process results ───────────────────────────────────────────────
            all_succeeded = True
            for node_id, result in zip(enabled_ids, results):
                if isinstance(result, BaseException):
                    all_succeeded = False
                    # Structured errors carry machine-readable metadata that
                    # the FE renders without showing a stack trace.
                    if isinstance(result, StructuredPipelineError):
                        error_payload = result.to_dict()
                        error_str = str(result)  # already JSON
                        error_event_extra = {
                            "error_type": error_payload.get("error_type"),
                            "error_detail": error_payload,
                        }
                    else:
                        error_payload = None
                        error_str = str(result)
                        error_event_extra = {}
                    logger.error(
                        "[DAGRunner] Node %r failed in run_id=%r: %s",
                        node_id,
                        self._run_id,
                        error_str,
                    )
                    self._emit(
                        "node.failed",
                        {
                            "node_id": node_id,
                            "error": error_str,
                            "will_retry": False,
                            **error_event_extra,
                        },
                    )
                    await crud.save_node_result(
                        self._run_id,
                        node_id=node_id,
                        status="failed",
                        error_message=error_str,
                    )
                    await crud.update_pipeline_run(
                        self._run_id,
                        status="failed",
                        error_message=(
                            error_str
                            if error_payload is not None
                            else f"Node '{node_id}' failed: {error_str}"
                        ),
                    )
                    self._emit(
                        "run.failed",
                        {
                            "failed_node": node_id,
                            "error": error_str,
                            **error_event_extra,
                        },
                    )
                    raise result  # type: ignore[misc]
                else:
                    self._node_outputs[node_id] = result

            layer_duration = time.time() - layer_start
            self._emit(
                "layer.completed",
                {
                    "layer_index": layer_idx,
                    "nodes": enabled_ids,
                    "duration_seconds": round(layer_duration, 2),
                    "all_succeeded": all_succeeded,
                },
            )

        # ── 5. Collect OUTPUT node result ────────────────────────────────────
        output_node = next(
            n for n in self._template.nodes if n.node_type == NodeType.OUTPUT
        )
        final_output = self._node_outputs.get(output_node.node_id, {})

        total_duration = time.time() - start_time
        await crud.update_pipeline_run(
            self._run_id,
            status="completed",
            completed_at=datetime.now(timezone.utc),
            duration_seconds=round(total_duration, 2),
        )
        self._emit(
            "run.completed",
            {
                "duration_seconds": round(total_duration, 2),
                "total_nodes_executed": len(self._node_outputs),
            },
        )
        logger.info(
            "[DAGRunner] Completed run_id=%r  duration=%.2fs  nodes=%d",
            self._run_id,
            total_duration,
            len(self._node_outputs),
        )
        return final_output

    # ─────────────────────────────────────────────────────────────────────────
    # Node execution
    # ─────────────────────────────────────────────────────────────────────────

    async def _execute_node_with_retry(
        self,
        node_config: PipelineNodeConfig,
        parent_outputs: dict[str, dict],  # type: ignore[type-arg]
    ) -> dict:  # type: ignore[type-arg]
        """Wrapper around _execute_node that implements exponential-backoff retry."""
        max_retries = node_config.retry_count
        last_error: Optional[BaseException] = None

        for attempt in range(max_retries + 1):
            try:
                return await self._execute_node(node_config, parent_outputs)
            except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
                last_error = exc
                # Fail-fast on structured pipeline errors (spec / report validation).
                # These errors describe contract violations the caller must fix
                # before any retry could succeed.
                if is_structured_pipeline_error(exc):
                    logger.info(
                        "[DAGRunner] Node %r raised structured error %s — "
                        "skipping retry.",
                        node_config.node_id,
                        type(exc).__name__,
                    )
                    raise
                if attempt < max_retries:
                    delay = 2**attempt  # 1s, 2s, 4s, …
                    logger.warning(
                        "[DAGRunner] Node %r attempt %d/%d failed, retrying in %ds: %s",
                        node_config.node_id,
                        attempt + 1,
                        max_retries + 1,
                        delay,
                        exc,
                    )
                    self._emit(
                        "node.failed",
                        {
                            "node_id": node_config.node_id,
                            "error": str(exc),
                            "will_retry": True,
                            "retry_attempt": attempt + 1,
                        },
                    )
                    await asyncio.sleep(delay)

        # All attempts exhausted
        raise last_error  # type: ignore[misc]

    async def _execute_node(
        self,
        node_config: PipelineNodeConfig,
        parent_outputs: dict[str, dict],  # type: ignore[type-arg]
    ) -> dict:  # type: ignore[type-arg]
        """Execute a single node and return its output dict."""
        node_id = node_config.node_id
        node_start = time.time()

        self._emit(
            "node.started",
            {
                "node_id": node_id,
                "node_type": node_config.node_type,
                "label": node_config.label,
                "agent_id": node_config.agent_id,
            },
        )
        await crud.update_pipeline_run(
            self._run_id,
            current_node=node_id,
            node_statuses={node_id: "running"},
        )

        try:
            if node_config.node_type == NodeType.OUTPUT:
                # OUTPUT node — merge all parent outputs as final result
                output = self._merge_inputs(parent_outputs)

            elif node_config.node_type == NodeType.PURE_PYTHON:
                output = await self._run_pure_python_node(node_config, parent_outputs)

            elif node_config.node_type == NodeType.AGENT:
                output = await self._run_agent_node(node_config, parent_outputs)

            else:
                raise ValueError(f"Unknown node_type: {node_config.node_type!r}")

            duration = time.time() - node_start
            # Resolve effective LLM profile for this node (for audit trail)
            _effective_llm = (
                self._node_llm_overrides.get(node_id)
                or (node_config.config_overrides or {}).get("llm_profile_id")
                or self._llm_profile_id
            )
            await crud.save_node_result(
                self._run_id,
                node_id=node_id,
                agent_id=node_config.agent_id,
                output=output,
                input_data=parent_outputs,
                status="completed",
                duration_seconds=round(duration, 2),
                llm_profile_id=_effective_llm,
            )
            # Persist any generated source files for playwright agent nodes.
            # Uses playwright_output_parser to handle all LLM output formats.
            if isinstance(output, dict) and node_config.agent_id in _PLAYWRIGHT_AGENT_IDS:
                await self._save_file_artifacts(node_id, node_config.agent_id or "", output)
            await crud.update_pipeline_run(
                self._run_id,
                completed_nodes=[*self._get_current_completed(), node_id],
                node_statuses={node_id: "completed"},
            )
            self._emit(
                "node.completed",
                {
                    "node_id": node_id,
                    "duration_seconds": round(duration, 2),
                    "output_preview": str(output)[:500],
                    "has_full_results": True,
                },
            )
            logger.info(
                "[DAGRunner] Node %r completed in %.2fs  run_id=%r",
                node_id,
                duration,
                self._run_id,
            )
            return output

        except asyncio.TimeoutError as exc:
            raise TimeoutError(
                f"Node '{node_id}' timed out after {node_config.timeout_seconds}s"
            ) from exc

    # ─────────────────────────────────────────────────────────────────────────
    # Execution strategies per node type
    # ─────────────────────────────────────────────────────────────────────────

    async def _run_agent_node(
        self,
        node_config: PipelineNodeConfig,
        parent_outputs: dict[str, dict],  # type: ignore[type-arg]
    ) -> dict:  # type: ignore[type-arg]
        """Run a CrewAI agent node."""
        if self._mock_mode:
            await asyncio.sleep(0.1)
            return {
                "mock": True,
                "node_id": node_config.node_id,
                "agent_id": node_config.agent_id,
                "status": "ok",
            }

        from app.core.agent_factory import AgentFactory

        # Resolve config overrides (e.g. per-node llm_profile_id)
        override_profile_id: Optional[str] = None
        if node_config.config_overrides:
            override_profile_id = node_config.config_overrides.get("llm_profile_id")
        # Derived-run per-node LLM overrides take precedence over config_overrides
        if node_config.node_id in self._node_llm_overrides:
            override_profile_id = self._node_llm_overrides[node_config.node_id]

        factory = AgentFactory(run_profile_id=self._llm_profile_id)

        # Build agent — respects per-agent & run-level profile overrides
        crewai_agent = await factory.build(
            node_config.agent_id,  # type: ignore[arg-type]
            override_profile_id=override_profile_id,
        )

        # Log config_overrides for debuggability (INFO so it appears without DEBUG mode)
        _overrides = node_config.config_overrides or {}
        logger.info(
            "[DAGRunner] node_id=%r  config_overrides keys=%s  task_instruction=%r",
            node_config.node_id,
            list(_overrides.keys()),
            _overrides.get("task_instruction"),
        )

        # If a task_instruction override is set, completely replace the CrewAI
        # system prompt so role/goal/backstory cannot steer the LLM elsewhere.
        # In CrewAI >=1.0 setting system_template replaces the default template
        # entirely; falling back to patching goal/backstory/role for older builds.
        _node_task_instr: str = _overrides.get("task_instruction") or ""
        if _node_task_instr:
            _override_system = (
                "You are a precise task executor. "
                f"Your only job is to follow this instruction:\n\n{_node_task_instr}\n\n"
                "Do NOT let any role, goal, or backstory override this instruction."
            )
            if hasattr(crewai_agent, "system_template"):
                crewai_agent.system_template = _override_system
            # Belt-and-suspenders: patch the underlying fields too
            if hasattr(crewai_agent, "role"):
                crewai_agent.role = "Precise Task Executor"
            if hasattr(crewai_agent, "goal"):
                crewai_agent.goal = _node_task_instr
            if hasattr(crewai_agent, "backstory"):
                crewai_agent.backstory = "You execute tasks exactly as instructed. You do not deviate."
            logger.info(
                "[DAGRunner] node_id=%r  system prompt fully overridden with task_instruction",
                node_config.node_id,
            )

        merged_input = self._merge_inputs(parent_outputs)

        # Ensure every agent receives the original document content,
        # even if it is N hops away from the INPUT node.
        if self._document_content and "document_content" not in merged_input:
            merged_input = {**merged_input, "document_content": self._document_content}

        import json

        from crewai import Crew, Process, Task  # type: ignore[import-untyped]

        # Fetch agent config so the goal drives the task instruction
        # Without this, powerful LLMs ignore role/goal/backstory and
        # perform a generic document analysis regardless of agent config.
        _agent_config = None
        if node_config.agent_id:
            _agent_config = await crud.get_agent_config(node_config.agent_id)

        # ── Build a structured task description ────────────────────────────────────
        # Separate the full document text from other metadata so the LLM
        # always receives the actual content rather than a path reference.
        doc_content: str = merged_input.get("document_content") or ""
        doc_name: str = merged_input.get("document_name") or ""
        metadata = {
            k: v
            for k, v in merged_input.items()
            if k not in ("document_content", "__sources__")
        }

        MAX_DOC_CHARS = 15_000   # characters of document body to send
        MAX_META_CHARS = 12_000  # characters for the metadata JSON blob (prev-node outputs)

        desc_parts: list[str] = []

        # Lead with the task instruction:
        # Priority: node config_overrides.task_instruction > agent.goal (fallback)
        _task_instr: str = (
            _overrides.get("task_instruction")
            or (_agent_config.goal if _agent_config else None)
            or ""
        )
        if _task_instr:
            desc_parts.append(f"Your task:\n{_task_instr}")

        if doc_name:
            desc_parts.append(f"Document: {doc_name}")

        if metadata:
            meta_str = json.dumps(metadata, default=str)
            if len(meta_str) > MAX_META_CHARS:
                meta_str = meta_str[:MAX_META_CHARS] + " ...[truncated]"
            desc_parts.append(f"Context:\n{meta_str}")

        if doc_content:
            if len(doc_content) > MAX_DOC_CHARS:
                doc_content = (
                    doc_content[:MAX_DOC_CHARS]
                    + "\n...[document truncated due to length]..."
                )
            desc_parts.append(f"Document Content:\n{doc_content}")
        else:
            # No parsed document content — fall back to JSON dump of full input
            fallback = json.dumps(merged_input, default=str)[:8000]
            desc_parts.append(f"Input Data:\n{fallback}")

        # ── Bookend: repeat task instruction AFTER document content ───────────
        # Small/local models tend to follow the LAST instruction seen in the
        # prompt more reliably than the first, especially when there is a large
        # document between the instruction and the end of the prompt.
        if _node_task_instr:
            desc_parts.append(
                f"---\nREMINDER — Your ONLY task is:\n{_node_task_instr}\n"
                "Ignore everything above that does not relate to this task."
            )

        task_description = "\n\n".join(desc_parts)
        logger.debug(
            "[DAGRunner] Built task description for node_id=%r agent_id=%r:\n%s",
            node_config.node_id,
            node_config.agent_id,
            task_description,
        )
        _DEFAULT_EXPECTED_OUTPUT = (
            "A single valid JSON object. "
            "Output ONLY the JSON - no markdown fences, no explanatory prose, "
            "no wrapper keys like 'raw_output' or 'result'. "
            "Start your response directly with '{' and end with '}'."
        )
        _expected_output: str = (
            _overrides.get("expected_output")
            or _DEFAULT_EXPECTED_OUTPUT
        )
        task = Task(
            description=task_description,
            expected_output=_expected_output,
            agent=crewai_agent,
        )

        crew = Crew(
            agents=[crewai_agent],
            tasks=[task],
            process=Process.sequential,
            verbose=bool(_node_task_instr),  # verbose only when debugging override
        )

        # CrewAI kickoff is synchronous — run in thread pool with timeout.
        # Instrument the call for LLM telemetry (latency + token usage).
        _llm_start = time.time()
        _llm_success = True
        _llm_error_type = ""
        _llm_error_msg = ""
        _crew_result = None

        try:
            _crew_result = await asyncio.wait_for(
                asyncio.to_thread(crew.kickoff),
                timeout=node_config.timeout_seconds,
            )
            logger.debug(
                "[DAGRunner] CrewAI result for node_id=%r agent_id=%r:\n%s",
                node_config.node_id,
                node_config.agent_id,
                _crew_result,
            )
        except Exception as _exc:  # noqa: BLE001
            _llm_success = False
            _llm_error_type = type(_exc).__name__
            _llm_error_msg = str(_exc)
            raise
        finally:
            _llm_latency_ms = int((time.time() - _llm_start) * 1000)

            # Extract token usage when CrewAI exposes it (>= 0.28)
            _prompt_tokens = _completion_tokens = _total_tokens = 0
            if _crew_result is not None and hasattr(_crew_result, "token_usage"):
                _usage = _crew_result.token_usage
                if _usage:
                    _prompt_tokens = int(getattr(_usage, "prompt_tokens", 0) or 0)
                    _completion_tokens = int(getattr(_usage, "completion_tokens", 0) or 0)
                    _total_tokens = int(getattr(_usage, "total_tokens", 0) or 0)

            _model_str = str(
                getattr(getattr(crewai_agent, "llm", None), "model", "") or ""
            )

            try:
                from app.services.event_bus import event_bus

                event_bus.emit_llm_call(
                    run_id=self._run_id,
                    node_id=node_config.node_id,
                    agent_id=str(node_config.agent_id or ""),
                    model=_model_str,
                    latency_ms=_llm_latency_ms,
                    prompt_tokens=_prompt_tokens,
                    completion_tokens=_completion_tokens,
                    total_tokens=_total_tokens,
                    success=_llm_success,
                    error_type=_llm_error_type,
                    error_message=_llm_error_msg,
                    task_description_len=len(task_description),
                    task_description_preview=task_description[:200],
                )
            except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
                pass

        return _carry_forward(merged_input, self._parse_crew_output(_crew_result))

    async def _run_pure_python_node(
        self,
        node_config: PipelineNodeConfig,
        parent_outputs: dict[str, dict],  # type: ignore[type-arg]
    ) -> dict:  # type: ignore[type-arg]
        """Run a pure-Python processing node (no LLM)."""
        builtin_functions: dict[str, Any] = {
            "ingestion_agent": self._builtin_ingestion,
            "ingestion_pipeline": self._builtin_ingestion,
            "artifact_pipeline": self._builtin_artifact,
            # Automation Testing API pipeline
            "md_api_spec_verifier": self._builtin_md_spec_verifier,
            "api_test_case_generator": self._builtin_api_test_case_generator,
            "api_test_runner": self._builtin_api_test_runner,
            "test_level_classifier": self._builtin_test_level_classifier,
            "export_html_docx": self._builtin_export_html_docx,
            "report_verifier": self._builtin_report_verifier,
            # Register additional builtins here
        }

        func = builtin_functions.get(node_config.agent_id or "")
        if func is None:
            raise ValueError(
                f"No builtin handler for pure_python node agent_id={node_config.agent_id!r}. "
                "Register it in DAGPipelineRunner.builtin_functions."
            )

        merged_input = self._merge_inputs(parent_outputs)
        output = await asyncio.wait_for(
            func(merged_input),
            timeout=node_config.timeout_seconds,
        )
        return _carry_forward(merged_input, output)

    # ─────────────────────────────────────────────────────────────────────────
    # Input gathering & merging
    # ─────────────────────────────────────────────────────────────────────────

    def _gather_inputs(self, node_id: str) -> dict[str, dict]:  # type: ignore[type-arg]
        """
        Collect outputs from all parent nodes.

        Returns:
            Mapping ``{ parent_node_id: parent_output_dict }`` for all
            parents whose output is already available.
        """
        parents = self._resolver.get_node_parents(node_id)
        return {
            parent_id: self._node_outputs[parent_id]
            for parent_id in parents
            if parent_id in self._node_outputs
        }

    def _merge_inputs(
        self,
        parent_outputs: dict[str, dict],  # type: ignore[type-arg]
    ) -> dict:  # type: ignore[type-arg]
        """
        Merge outputs from multiple parent nodes into one input dict.

        Single parent → pass-through (no wrapping).
        Multiple parents → namespace by parent_id + shallow flat merge.
        """
        if not parent_outputs:
            return {}

        if len(parent_outputs) == 1:
            return next(iter(parent_outputs.values()))

        merged: dict = {"__sources__": {}}  # type: ignore[type-arg]
        flat: dict = {}  # type: ignore[type-arg]
        for parent_id, output in parent_outputs.items():
            merged["__sources__"][parent_id] = output
            if isinstance(output, dict):
                flat.update(output)

        merged.update(flat)
        return merged

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _get_node(self, node_id: str) -> PipelineNodeConfig:
        """Return the PipelineNodeConfig for *node_id*.

        Raises:
            ValueError: If node_id is not in the template.
        """
        for node in self._template.nodes:
            if node.node_id == node_id:
                return node
        raise ValueError(f"Node not found in template: {node_id!r}")

    def _get_current_completed(self) -> list[str]:
        """Return node_ids whose output is already cached."""
        return list(self._node_outputs.keys())

    def _emit(self, event: str, data: dict) -> None:  # type: ignore[type-arg]
        """Fire a WebSocket event and forward to Kafka for observability."""
        if self._progress_callback is not None:
            try:
                self._progress_callback(event, {"run_id": self._run_id, **data})
            except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
                logger.warning("[DAGRunner] Progress callback error: %s", exc)
        self._kafka_emit(event, data)

    def _kafka_emit(self, event: str, data: dict) -> None:  # type: ignore[type-arg]
        """
        Route pipeline/node events to the appropriate Kafka topic.

        run.*   → pipeline_events topic
        node.*  → node_events topic
        layer.* → skipped (too verbose; infer from node events)
        """
        try:
            from app.services.event_bus import event_bus

            if event.startswith("run."):
                event_bus.emit_pipeline_event(
                    event_type=event,
                    run_id=self._run_id,
                    template_id=data.get("template_id") or self._template.template_id,
                    document_name=self._document_name,
                    total_nodes=int(data.get("total_nodes", 0)),
                    total_layers=int(data.get("total_layers", 0)),
                    duration_seconds=float(data.get("duration_seconds", 0.0)),
                    error=str(data.get("error", "")),
                    failed_node=str(data.get("failed_node", "")),
                    extra={
                        k: v for k, v in data.items()
                        if k not in (
                            "template_id", "total_nodes", "total_layers",
                            "duration_seconds", "error", "failed_node",
                        )
                    },
                )

            elif event.startswith("node."):
                node_id = str(data.get("node_id", ""))
                # Lookup node config for richer metadata when the event
                # doesn't carry node_type / label (e.g. node.completed).
                node_cfg = None
                if node_id:
                    try:
                        node_cfg = self._get_node(node_id)
                    except ValueError:
                        pass

                _STATUS_MAP: dict[str, str] = {
                    "node.started": "running",
                    "node.completed": "completed",
                    "node.failed": "failed",
                    "node.skipped": "skipped",
                }

                event_bus.emit_node_event(
                    event_type=event,
                    run_id=self._run_id,
                    node_id=node_id,
                    node_type=str(
                        data.get("node_type")
                        or (getattr(node_cfg, "node_type", None) if node_cfg else "")
                        or ""
                    ),
                    agent_id=str(
                        data.get("agent_id")
                        or (getattr(node_cfg, "agent_id", None) if node_cfg else "")
                        or ""
                    ),
                    label=str(getattr(node_cfg, "label", "") or ""),
                    status=_STATUS_MAP.get(event, ""),
                    duration_ms=int(float(data.get("duration_seconds", 0)) * 1000),
                    retry_attempt=int(data.get("retry_attempt", 0)),
                    will_retry=bool(data.get("will_retry", False)),
                    error_detail=str(data.get("error", "")),
                    output_preview=str(data.get("output_preview", "")),
                )
            # layer.* events: skip — too high-frequency, infer from node events

        except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            logger.debug("[DAGRunner] Kafka emit error event=%r: %s", event, exc)

    async def _handle_cancel(self) -> None:
        """Transition the run to CANCELLED state and emit the event."""
        await crud.update_pipeline_run(
            self._run_id,
            status="cancelled",
            completed_at=datetime.now(timezone.utc),
        )
        self._emit(
            "run.cancelled",
            {
                "completed_nodes": list(self._node_outputs.keys()),
                "partial_results_available": len(self._node_outputs) > 0,
            },
        )
        logger.info(
            "[DAGRunner] Cancelled run_id=%r  completed_nodes=%d",
            self._run_id,
            len(self._node_outputs),
        )

    def _build_result(self) -> dict:  # type: ignore[type-arg]
        """Return a summary dict (used when run was cancelled/failed early)."""
        return {
            "run_id": self._run_id,
            "node_outputs": self._node_outputs,
            "status": "cancelled",
        }

    async def _load_inherited_nodes(self, layers: list[list[str]]) -> None:
        """Load node outputs from the parent run for all nodes that precede
        ``rerun_from_node`` in the execution order (inclusive of INPUT, exclusive
        of ``rerun_from_node`` itself and all its downstream nodes).

        Populates ``self._node_outputs`` and ``self._inherited_nodes`` so the
        layer-execution loop can skip them and carry their data forward.
        """
        if not self._parent_run_id or not self._rerun_from_node:
            return

        # Build set of all nodes that appear *before* rerun_from_node in the
        # flattened layer order.  Nodes in the same layer as rerun_from_node
        # that are NOT rerun_from_node itself are also inherited.
        inherited: set[str] = set()
        for layer in layers:
            if self._rerun_from_node in layer:
                # All other nodes in this layer (siblings) are also inherited
                for nid in layer:
                    if nid != self._rerun_from_node:
                        inherited.add(nid)
                break
            inherited.update(layer)

        # INPUT node is always seeded from the new run's initial_input — skip
        input_node = next(
            n for n in self._template.nodes if n.node_type == NodeType.INPUT
        )
        inherited.discard(input_node.node_id)

        # Fetch outputs from parent and populate caches
        for node_id in inherited:
            parent_result = await crud.get_node_result(self._parent_run_id, node_id)
            if parent_result is None or parent_result.output is None:
                logger.warning(
                    "[DAGRunner] Parent run %r has no result for node %r — "
                    "will re-execute instead of inheriting.",
                    self._parent_run_id,
                    node_id,
                )
                continue

            self._node_outputs[node_id] = (
                parent_result.output if isinstance(parent_result.output, dict) else {}
            )
            self._inherited_nodes.add(node_id)

            # Persist an inherited-marker result for this node in the new run
            await crud.save_node_result(
                self._run_id,
                node_id=node_id,
                agent_id=parent_result.agent_id,
                output=parent_result.output,
                input_data=parent_result.input_data,
                status="completed",
                duration_seconds=parent_result.duration_seconds,
                llm_profile_id=parent_result.llm_profile_id,
                is_inherited=True,
                source_run_id=self._parent_run_id,
            )

        logger.info(
            "[DAGRunner] run_id=%r  inherited %d nodes from parent %r: %s",
            self._run_id,
            len(self._inherited_nodes),
            self._parent_run_id,
            sorted(self._inherited_nodes),
        )

    def _parse_crew_output(self, result: Any) -> dict:  # type: ignore[type-arg]
        """Parse a CrewAI kickoff result into a plain dict.

        Handles (in order):
            1. Direct valid JSON string.
            2. JSON wrapped in a markdown code fence (```json ... ```).
            3. First ```{...}``` JSON block embedded anywhere in prose.
            4. Falls back to ```{"raw_output": text}``` as a last resort.
        """
        import json
        import re

        raw: str = result.raw if hasattr(result, "raw") else str(result)
        stripped = raw.strip()

        # -- 1. Direct JSON parse ------------------------------------------------
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                return parsed
            return {"result": parsed}
        except (json.JSONDecodeError, TypeError):
            pass

        # -- 2. Markdown code fence ----------------------------------------------
        fence_match = re.search(
            r"^```(?:json|js|javascript|ts|typescript|text|python)?\s*\n"
            r"([\s\S]*?)\n?```\s*$",
            stripped,
        )
        if fence_match:
            inner = fence_match.group(1).strip()
            try:
                parsed = json.loads(inner)
                if isinstance(parsed, dict):
                    return parsed
                return {"result": parsed}
            except (json.JSONDecodeError, TypeError):
                pass

        # -- 3. First embedded JSON object in prose ------------------------------
        obj_match = re.search(r"\{[\s\S]+\}", stripped)
        if obj_match:
            try:
                parsed = json.loads(obj_match.group(0))
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass

        # -- 4. Give up -- preserve raw text ------------------------------------
        return {"raw_output": raw}

    # ─────────────────────────────────────────────────────────────────────────
    # Builtin pure-Python node handlers
    # ─────────────────────────────────────────────────────────────────────────

    async def _builtin_ingestion(
        self,
        input_data: dict,  # type: ignore[type-arg]
    ) -> dict:  # type: ignore[type-arg]
        """Delegate to the V2 IngestionCrew (backward-compatible)."""
        from app.crews.ingestion_crew import IngestionCrew

        crew = IngestionCrew(
            run_id=self._run_id,
            run_profile_id=self._llm_profile_id,
            progress_callback=self._progress_callback,
            mock_mode=self._mock_mode,
        )
        # Forward mock_mode so IngestionCrew.run() reads it from input_data
        merged = {**input_data, "mock_mode": self._mock_mode}
        return await asyncio.to_thread(crew.run, merged)

    # ─────────────────────────────────────────────────────────────────────────
    # File artifact persistence
    # ─────────────────────────────────────────────────────────────────────────

    async def _save_file_artifacts(
        self,
        node_id: str,
        agent_id: str,
        output: dict,  # type: ignore[type-arg]
    ) -> None:
        """Persist playwright source files from node output to MinIO.

        Uses playwright_output_parser to handle all LLM output formats.
        Files are uploaded to MinIO under ``runs/<run_id>/playwright/``.
        """
        import asyncio
        from app.core.playwright_output_parser import extract_playwright_files
        from app.services.storage_service import storage

        files_map = extract_playwright_files(agent_id, output)
        if not files_map:
            logger.warning(
                "[DAGRunner] No artifact files extracted for node_id=%r agent_id=%r",
                node_id,
                agent_id,
            )
            return

        loop = asyncio.get_running_loop()
        files_written: list[str] = []
        for filename, content in files_map.items():
            await loop.run_in_executor(
                None,
                storage.upload_file_content,
                self._run_id,
                filename,
                content,
                "playwright",
                "text/plain",
            )
            files_written.append(filename)

        logger.info(
            "[DAGRunner] Uploaded %d artifact file(s) to MinIO for node_id=%r run_id=%r: %s",
            len(files_written),
            node_id,
            self._run_id,
            files_written,
        )

    async def _builtin_artifact(
        self,
        input_data: dict,  # type: ignore[type-arg]
    ) -> dict:  # type: ignore[type-arg]
        """Run the ArtifactCrew to generate unit test files + test case document."""
        from app.crews.artifact_crew import ArtifactCrew

        crew = ArtifactCrew(
            run_id=self._run_id,
            run_profile_id=self._llm_profile_id,
            progress_callback=self._progress_callback,
            mock_mode=self._mock_mode,
        )
        return await asyncio.to_thread(crew.run, input_data)

    # ─────────────────────────────────────────────────────────────────────────
    # Automation Testing API — builtin pure-python handlers
    # ─────────────────────────────────────────────────────────────────────────

    async def _builtin_md_spec_verifier(
        self,
        input_data: dict,  # type: ignore[type-arg]
    ) -> dict:  # type: ignore[type-arg]
        """Validate MD API spec; raise MDSpecValidationError if invalid."""
        from app.crews.md_spec_verifier_crew import MDSpecVerifierCrew

        crew = MDSpecVerifierCrew(
            run_id=self._run_id,
            run_profile_id=self._llm_profile_id,
            progress_callback=self._progress_callback,
            mock_mode=self._mock_mode,
        )
        # Forward original document content if INPUT didn't pre-load it.
        merged: dict = dict(input_data)  # type: ignore[type-arg]
        if self._document_content and "document_content" not in merged:
            merged["document_content"] = self._document_content
        if self._document_name and "document_name" not in merged:
            merged["document_name"] = self._document_name
        return await asyncio.to_thread(crew.run, merged)

    async def _builtin_api_test_case_generator(
        self,
        input_data: dict,  # type: ignore[type-arg]
    ) -> dict:  # type: ignore[type-arg]
        """Generate API test cases deterministically from md_spec_parsed."""
        from app.crews.api_test_case_crew import ApiTestCaseCrew

        crew = ApiTestCaseCrew(
            run_id=self._run_id,
            run_profile_id=self._llm_profile_id,
            progress_callback=self._progress_callback,
            mock_mode=self._mock_mode,
        )
        # Forward the original document so the generator can recover the
        # `Base URL:` line that the validator does not capture.
        merged: dict = dict(input_data)  # type: ignore[type-arg]
        if self._document_content and "document_content" not in merged:
            merged["document_content"] = self._document_content
        return await asyncio.to_thread(crew.run, merged)

    async def _builtin_api_test_runner(
        self,
        input_data: dict,  # type: ignore[type-arg]
    ) -> dict:  # type: ignore[type-arg]
        """Execute every executable API test case via httpx."""
        from app.crews.api_test_runner_crew import ApiTestRunnerCrew

        crew = ApiTestRunnerCrew(
            run_id=self._run_id,
            run_profile_id=self._llm_profile_id,
            progress_callback=self._progress_callback,
            mock_mode=self._mock_mode,
        )
        # Forward the original document so the runner can recover the
        # Base URL declared in the spec body.
        merged: dict = dict(input_data)  # type: ignore[type-arg]
        if self._document_content and "document_content" not in merged:
            merged["document_content"] = self._document_content
        return await asyncio.to_thread(crew.run, merged)

    async def _builtin_test_level_classifier(
        self,
        input_data: dict,  # type: ignore[type-arg]
    ) -> dict:  # type: ignore[type-arg]
        """Tag each TestCase with ``test_level`` + ``executable`` flag."""
        from app.crews.test_level_classifier_crew import TestLevelClassifierCrew

        crew = TestLevelClassifierCrew(
            run_id=self._run_id,
            run_profile_id=self._llm_profile_id,
            progress_callback=self._progress_callback,
            mock_mode=self._mock_mode,
        )
        return await asyncio.to_thread(crew.run, input_data)

    async def _builtin_export_html_docx(
        self,
        input_data: dict,  # type: ignore[type-arg]
    ) -> dict:  # type: ignore[type-arg]
        """Export the final report to HTML + DOCX and upload to MinIO."""
        from app.crews.export_crew import ExportCrew

        crew = ExportCrew(
            run_id=self._run_id,
            run_profile_id=self._llm_profile_id,
            progress_callback=self._progress_callback,
            mock_mode=self._mock_mode,
        )
        return await asyncio.to_thread(crew.run, input_data)

    async def _builtin_report_verifier(
        self,
        input_data: dict,  # type: ignore[type-arg]
    ) -> dict:  # type: ignore[type-arg]
        """Verify the report carries all 3 mandatory components."""
        from app.crews.report_verifier_crew import ReportVerifierCrew

        crew = ReportVerifierCrew(
            run_id=self._run_id,
            run_profile_id=self._llm_profile_id,
            progress_callback=self._progress_callback,
            mock_mode=self._mock_mode,
        )
        return await asyncio.to_thread(crew.run, input_data)
