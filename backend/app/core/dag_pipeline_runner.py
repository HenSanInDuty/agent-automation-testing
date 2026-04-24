from __future__ import annotations

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

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from app.core.dag_resolver import DAGResolver, DAGValidationError
from app.core.signal_manager import PipelineSignal, signal_manager
from app.db import crud
from app.db.models import NodeType, PipelineNodeConfig, PipelineTemplateDocument

logger = logging.getLogger(__name__)

# Callback type: (event_type: str, data: dict) -> None
ProgressCallback = Callable[[str, dict[str, Any]], None]


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
    ) -> None:
        self._run_id = run_id
        self._template = template
        self._llm_profile_id = llm_profile_id
        self._progress_callback = progress_callback
        self._mock_mode = mock_mode

        # Node outputs cache: { node_id: output_dict }
        self._node_outputs: dict[str, dict] = {}  # type: ignore[type-arg]

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
        self._document_content = initial_input.get("document_content") or ""        self._document_name = initial_input.get("document_name") or ""
        # ── 4. Execute layer by layer ────────────────────────────────────────
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
                    error_str = str(result)
                    logger.error(
                        "[DAGRunner] Node %r failed in run_id=%r: %s",
                        node_id,
                        self._run_id,
                        error_str,
                    )
                    self._emit(
                        "node.failed",
                        {"node_id": node_id, "error": error_str, "will_retry": False},
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
                        error_message=f"Node '{node_id}' failed: {error_str}",
                    )
                    self._emit(
                        "run.failed",
                        {"failed_node": node_id, "error": error_str},
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
            except Exception as exc:  # noqa: BLE001
                last_error = exc
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
            await crud.save_node_result(
                self._run_id,
                node_id=node_id,
                agent_id=node_config.agent_id,
                output=output,
                input_data=parent_outputs,
                status="completed",
                duration_seconds=round(duration, 2),
            )
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

        except asyncio.TimeoutError:
            raise TimeoutError(
                f"Node '{node_id}' timed out after {node_config.timeout_seconds}s"
            )

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

        factory = AgentFactory(run_profile_id=self._llm_profile_id)

        # Build agent — respects per-agent & run-level profile overrides
        crewai_agent = await factory.build(
            node_config.agent_id,  # type: ignore[arg-type]
            override_profile_id=override_profile_id,
        )

        merged_input = self._merge_inputs(parent_outputs)

        # Ensure every agent receives the original document content,
        # even if it is N hops away from the INPUT node.
        if self._document_content and "document_content" not in merged_input:
            merged_input = {**merged_input, "document_content": self._document_content}

        import json

        from crewai import Crew, Process, Task  # type: ignore[import-untyped]


        from app.db import crud as _crud

        # Fetch agent config so the goal drives the task instruction
        # Without this, powerful LLMs ignore role/goal/backstory and
        # perform a generic document analysis regardless of agent config.
        _agent_config = None
        if node_config.agent_id:
            _agent_config = await _crud.get_agent_config(node_config.agent_id)

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
        MAX_META_CHARS = 2_000   # characters for the metadata JSON blob

        desc_parts: list[str] = []

        # Lead with the agent goal -- this IS the task instruction
        if _agent_config and _agent_config.goal:
            desc_parts.append(f"Your task:\n{_agent_config.goal}")

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

        task_description = "\n\n".join(desc_parts)

        task = Task(
            description=task_description,
            expected_output=(
                "A single valid JSON object containing your analysis results. "
                "Output ONLY the JSON - no markdown fences, no explanatory prose, "
                "no wrapper keys like 'raw_output' or 'result'. "
                "Start your response directly with '{' and end with '}'."
            ),
            agent=crewai_agent,
        )

        crew = Crew(
            agents=[crewai_agent],
            tasks=[task],
            process=Process.sequential,
            verbose=False,
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
            except Exception:  # noqa: BLE001
                pass

        return self._parse_crew_output(_crew_result)

    async def _run_pure_python_node(
        self,
        node_config: PipelineNodeConfig,
        parent_outputs: dict[str, dict],  # type: ignore[type-arg]
    ) -> dict:  # type: ignore[type-arg]
        """Run a pure-Python processing node (no LLM)."""
        builtin_functions: dict[str, Any] = {
            "ingestion_agent": self._builtin_ingestion,
            # Register additional builtins here
        }

        func = builtin_functions.get(node_config.agent_id or "")
        if func is None:
            raise ValueError(
                f"No builtin handler for pure_python node agent_id={node_config.agent_id!r}. "
                "Register it in DAGPipelineRunner.builtin_functions."
            )

        merged_input = self._merge_inputs(parent_outputs)
        return await asyncio.wait_for(
            func(merged_input),
            timeout=node_config.timeout_seconds,
        )

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
            except Exception as exc:  # noqa: BLE001
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

        except Exception as exc:  # noqa: BLE001
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
        return await crew.run(input_data)  # type: ignore[misc]
