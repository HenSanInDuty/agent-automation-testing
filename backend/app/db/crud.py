"""
db/crud.py – Async CRUD operations using Beanie ODM.

All functions are async and work directly with Beanie Documents.
No Session parameter needed — Beanie manages the connection globally
after :func:`app.db.database.init_db` has been called at startup.

Sections
--------
* LLM Profiles
* Agent Configs
* Stage Configs
* Pipeline Runs
* Pipeline Results
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.db.models import (
    AgentConfigDocument,
    LLMProfileDocument,
    PipelineResultDocument,
    PipelineRunDocument,
    StageConfigDocument,
)
from app.schemas.pipeline import AgentRunStatus, PipelineStatus

logger = logging.getLogger(__name__)


def _now() -> datetime:
    """Return the current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# LLM Profiles
# ─────────────────────────────────────────────────────────────────────────────


async def get_llm_profile(profile_id: str) -> Optional[LLMProfileDocument]:
    """Get a single LLM profile by its MongoDB ObjectId string.

    Args:
        profile_id: Hex string representation of a MongoDB ``ObjectId``.

    Returns:
        The matching :class:`~app.db.models.LLMProfileDocument`, or ``None``
        if the ID is invalid or the document does not exist.
    """
    from beanie import PydanticObjectId

    try:
        return await LLMProfileDocument.get(PydanticObjectId(profile_id))
    except Exception:
        return None


async def get_llm_profile_by_name(name: str) -> Optional[LLMProfileDocument]:
    """Get a single LLM profile by its unique name.

    Args:
        name: The human-readable profile name (e.g. ``"GPT-4o (Default)"``).

    Returns:
        The matching document or ``None``.
    """
    return await LLMProfileDocument.find_one(LLMProfileDocument.name == name)


async def get_default_llm_profile() -> Optional[LLMProfileDocument]:
    """Return the profile marked as ``is_default=True``, or ``None``.

    Only one profile should be marked as default at any given time; this
    function returns the first match if somehow more than one exists.
    """
    return await LLMProfileDocument.find_one(
        LLMProfileDocument.is_default == True  # noqa: E712
    )


async def get_all_llm_profiles(
    skip: int = 0,
    limit: int = 100,
) -> tuple[list[LLMProfileDocument], int]:
    """Return a paginated list of LLM profiles and the total document count.

    Args:
        skip: Number of documents to skip (for pagination).
        limit: Maximum number of documents to return.

    Returns:
        A ``(items, total)`` tuple where *total* is the unfiltered count.
    """
    total = await LLMProfileDocument.count()
    items = await LLMProfileDocument.find_all().skip(skip).limit(limit).to_list()
    return items, total


async def create_llm_profile(data: dict) -> LLMProfileDocument:
    """Insert a new LLM profile document.

    If ``data["is_default"]`` is truthy, all other profiles are unset from
    the default position before the new document is inserted.

    Args:
        data: Dict of field values matching :class:`~app.db.models.LLMProfileDocument`.

    Returns:
        The newly-inserted document (with ``id`` populated by MongoDB).
    """
    if data.get("is_default"):
        await LLMProfileDocument.find(
            LLMProfileDocument.is_default == True  # noqa: E712
        ).update_many({"$set": {"is_default": False, "updated_at": _now()}})

    doc = LLMProfileDocument(**data)
    await doc.insert()
    return doc


async def update_llm_profile(
    profile_id: str,
    data: dict,
) -> Optional[LLMProfileDocument]:
    """Partially update an LLM profile.

    Only the keys present in *data* are written; other fields are left
    untouched.  If ``data["is_default"]`` is truthy, the default flag is
    cleared from all other profiles first.

    Args:
        profile_id: MongoDB ObjectId string of the document to update.
        data: Mapping of field names → new values (partial update).

    Returns:
        The refreshed document after the update, or ``None`` if not found.
    """
    doc = await get_llm_profile(profile_id)
    if doc is None:
        return None

    if data.get("is_default"):
        await LLMProfileDocument.find(
            LLMProfileDocument.is_default == True  # noqa: E712
        ).update_many({"$set": {"is_default": False, "updated_at": _now()}})

    data["updated_at"] = _now()
    await doc.update({"$set": data})
    await doc.sync()
    return doc


async def delete_llm_profile(profile_id: str) -> bool:
    """Delete an LLM profile by its ObjectId string.

    Args:
        profile_id: MongoDB ObjectId string.

    Returns:
        ``True`` if the document was found and deleted; ``False`` otherwise.
    """
    doc = await get_llm_profile(profile_id)
    if doc is None:
        return False
    await doc.delete()
    return True


async def set_default_llm_profile(profile_id: str) -> Optional[LLMProfileDocument]:
    """Mark the given profile as the global default and unset all others.

    Args:
        profile_id: MongoDB ObjectId string of the profile to promote.

    Returns:
        The updated document, or ``None`` if *profile_id* does not exist.
    """
    doc = await get_llm_profile(profile_id)
    if doc is None:
        return None

    # Unset every currently-active default (including the target, just in case)
    await LLMProfileDocument.find(
        LLMProfileDocument.is_default == True  # noqa: E712
    ).update_many({"$set": {"is_default": False, "updated_at": _now()}})

    await doc.update({"$set": {"is_default": True, "updated_at": _now()}})
    await doc.sync()
    return doc


# ─────────────────────────────────────────────────────────────────────────────
# Agent Configs
# ─────────────────────────────────────────────────────────────────────────────


async def get_agent_config(agent_id: str) -> Optional[AgentConfigDocument]:
    """Get a single agent config by its unique ``agent_id`` slug.

    Args:
        agent_id: Human-readable slug such as ``"requirement_analyzer"``.

    Returns:
        The matching document or ``None``.
    """
    return await AgentConfigDocument.find_one(AgentConfigDocument.agent_id == agent_id)


async def get_agent_config_by_id(doc_id: str) -> Optional[AgentConfigDocument]:
    """Get a single agent config by its MongoDB ObjectId string.

    Args:
        doc_id: Hex string representation of a MongoDB ``ObjectId``.

    Returns:
        The matching document or ``None`` if the ID is invalid / not found.
    """
    from beanie import PydanticObjectId

    try:
        return await AgentConfigDocument.get(PydanticObjectId(doc_id))
    except Exception:
        return None


async def get_all_agent_configs(
    stage: Optional[str] = None,
    enabled_only: bool = False,
) -> list[AgentConfigDocument]:
    """Get all agent configs, optionally filtered by stage and/or enabled status.

    Results are sorted by ``stage`` ascending so agents are grouped logically
    when iterated.

    Args:
        stage: If provided, only return agents whose ``stage`` matches.
        enabled_only: If ``True``, exclude disabled agents.

    Returns:
        Flat list of :class:`~app.db.models.AgentConfigDocument` instances.
    """
    filters: list[Any] = []
    if stage:
        filters.append(AgentConfigDocument.stage == stage)
    if enabled_only:
        filters.append(AgentConfigDocument.enabled == True)  # noqa: E712

    if filters:
        return await AgentConfigDocument.find(*filters).sort("+stage").to_list()
    return await AgentConfigDocument.find_all().sort("+stage").to_list()


async def get_agent_configs_for_stage(
    stage: str,
    enabled_only: bool = True,
) -> list[AgentConfigDocument]:
    """Get agent configs for a specific pipeline stage.

    Convenience wrapper around :func:`get_all_agent_configs` used by the
    pipeline runner when building a CrewAI crew.

    Args:
        stage: Stage identifier (``"ingestion"``, ``"testcase"``, etc.).
        enabled_only: When ``True`` (the default), skip disabled agents.

    Returns:
        List of agent documents for the given stage.
    """
    filters: list[Any] = [AgentConfigDocument.stage == stage]
    if enabled_only:
        filters.append(AgentConfigDocument.enabled == True)  # noqa: E712
    return await AgentConfigDocument.find(*filters).to_list()


async def create_agent_config(data: dict) -> AgentConfigDocument:
    """Create a new custom agent config (``is_custom=True``).

    Callers should not pass ``is_custom`` in *data*; this function always
    sets it to ``True`` to distinguish user-created agents from seeded ones.

    Args:
        data: Dict of field values matching :class:`~app.db.models.AgentConfigDocument`.

    Returns:
        The newly-inserted document.
    """
    data["is_custom"] = True
    doc = AgentConfigDocument(**data)
    await doc.insert()
    return doc


async def upsert_agent_config(defaults: dict) -> AgentConfigDocument:
    """Insert an agent config, or return the existing one if already present.

    This is the idempotent seeder helper — calling it multiple times for
    the same ``agent_id`` always leaves the database in the same state.
    Existing documents (including any admin customisations) are never
    overwritten.

    Args:
        defaults: Full dict of default field values including ``agent_id``.

    Returns:
        The existing document if found, or the newly-created document.
    """
    existing = await get_agent_config(defaults["agent_id"])
    if existing is not None:
        return existing

    doc = AgentConfigDocument(**defaults)
    await doc.insert()
    return doc


async def update_agent_config(
    agent_id: str,
    data: dict,
) -> Optional[AgentConfigDocument]:
    """Partially update an agent config identified by its slug.

    Args:
        agent_id: Unique agent slug (e.g. ``"rule_parser"``).
        data: Fields to update.  ``updated_at`` is set automatically.

    Returns:
        The refreshed document, or ``None`` if *agent_id* does not exist.
    """
    doc = await get_agent_config(agent_id)
    if doc is None:
        return None
    data["updated_at"] = _now()
    await doc.update({"$set": data})
    await doc.sync()
    return doc


async def delete_agent_config(agent_id: str) -> bool:
    """Delete a custom agent config.

    Builtin (seeded) agents cannot be deleted; a :class:`ValueError` is
    raised instead to prevent accidental removal of default configuration.

    Args:
        agent_id: Unique agent slug to delete.

    Returns:
        ``True`` if the document was deleted.

    Raises:
        ValueError: If the agent exists but ``is_custom=False``.
    """
    doc = await get_agent_config(agent_id)
    if doc is None:
        return False
    if not doc.is_custom:
        raise ValueError(f"Cannot delete builtin agent: {agent_id}")
    await doc.delete()
    return True


async def reset_agent_config(
    agent_id: str,
    defaults: dict,
) -> Optional[AgentConfigDocument]:
    """Reset an agent config back to its seeded defaults.

    Clears ``llm_profile_id`` (so the agent falls back to the global default
    profile) and restores all prompt and behaviour fields to *defaults*.

    Args:
        agent_id: Unique agent slug to reset.
        defaults: Dict of original seed values for this agent.

    Returns:
        The refreshed document, or ``None`` if *agent_id* does not exist.
    """
    doc = await get_agent_config(agent_id)
    if doc is None:
        return None

    resettable = (
        "display_name",
        "stage",
        "role",
        "goal",
        "backstory",
        "enabled",
        "verbose",
        "max_iter",
    )
    reset_data: dict[str, Any] = {k: defaults[k] for k in resettable if k in defaults}
    reset_data["llm_profile_id"] = None
    reset_data["updated_at"] = _now()

    await doc.update({"$set": reset_data})
    await doc.sync()
    return doc


async def reset_all_agent_configs(
    all_defaults: list[dict],
) -> list[AgentConfigDocument]:
    """Reset every agent config to its seeded defaults in a single pass.

    Iterates all documents in the collection, finds the corresponding entry
    in *all_defaults* by ``agent_id``, and applies the reset.  Documents
    with no matching default entry are left unchanged.

    Args:
        all_defaults: List of seed-default dicts (one per agent).

    Returns:
        All agent config documents after the reset (re-fetched from DB).
    """
    defaults_map: dict[str, dict] = {d["agent_id"]: d for d in all_defaults}
    docs = await get_all_agent_configs()

    resettable = (
        "display_name",
        "stage",
        "role",
        "goal",
        "backstory",
        "enabled",
        "verbose",
        "max_iter",
    )

    for doc in docs:
        seed = defaults_map.get(doc.agent_id)
        if seed is None:
            continue
        reset_data: dict[str, Any] = {k: seed[k] for k in resettable if k in seed}
        reset_data["llm_profile_id"] = None
        reset_data["updated_at"] = _now()
        await doc.update({"$set": reset_data})

    # Re-fetch after all updates so callers receive fresh data
    return await get_all_agent_configs()


# ─────────────────────────────────────────────────────────────────────────────
# Stage Configs
# ─────────────────────────────────────────────────────────────────────────────


async def get_stage_config(stage_id: str) -> Optional[StageConfigDocument]:
    """Get a stage config by its unique ``stage_id``.

    Args:
        stage_id: Stage identifier such as ``"testcase"`` or ``"reporting"``.

    Returns:
        The matching document or ``None``.
    """
    return await StageConfigDocument.find_one(StageConfigDocument.stage_id == stage_id)


async def get_all_stage_configs(
    enabled_only: bool = False,
) -> list[StageConfigDocument]:
    """Get all stage configs sorted by ``order`` ascending.

    Args:
        enabled_only: When ``True``, exclude stages where ``enabled=False``.

    Returns:
        List of :class:`~app.db.models.StageConfigDocument` in execution order.
    """
    if enabled_only:
        return (
            await StageConfigDocument.find(
                StageConfigDocument.enabled == True  # noqa: E712
            )
            .sort("+order")
            .to_list()
        )
    return await StageConfigDocument.find_all().sort("+order").to_list()


async def create_stage_config(data: dict) -> StageConfigDocument:
    """Create a new custom stage config (``is_builtin=False``).

    Args:
        data: Dict of field values matching :class:`~app.db.models.StageConfigDocument`.

    Returns:
        The newly-inserted document.
    """
    data["is_builtin"] = False
    doc = StageConfigDocument(**data)
    await doc.insert()
    return doc


async def upsert_stage_config(defaults: dict) -> StageConfigDocument:
    """Insert a stage config, or return the existing one if already present.

    Idempotent seeder helper — safe to call multiple times.  Existing
    documents (including any admin changes) are never overwritten.

    Args:
        defaults: Full dict of default field values including ``stage_id``.

    Returns:
        The existing document if found, or the newly-created document.
    """
    existing = await get_stage_config(defaults["stage_id"])
    if existing is not None:
        return existing
    doc = StageConfigDocument(**defaults)
    await doc.insert()
    return doc


async def update_stage_config(
    stage_id: str,
    data: dict,
) -> Optional[StageConfigDocument]:
    """Partially update a stage config.

    Args:
        stage_id: Stage identifier to update.
        data: Fields to update.  ``updated_at`` is set automatically.

    Returns:
        The refreshed document, or ``None`` if *stage_id* does not exist.
    """
    doc = await get_stage_config(stage_id)
    if doc is None:
        return None
    data["updated_at"] = _now()
    await doc.update({"$set": data})
    await doc.sync()
    return doc


async def delete_stage_config(stage_id: str) -> bool:
    """Delete a custom stage config.

    Builtin stages cannot be deleted; a :class:`ValueError` is raised to
    prevent accidental removal of core pipeline infrastructure.

    Args:
        stage_id: Stage identifier to delete.

    Returns:
        ``True`` if the document was deleted.

    Raises:
        ValueError: If the stage exists but ``is_builtin=True``.
    """
    doc = await get_stage_config(stage_id)
    if doc is None:
        return False
    if doc.is_builtin:
        raise ValueError(f"Cannot delete builtin stage: {stage_id}")
    await doc.delete()
    return True


async def reorder_stages(stage_orders: list[dict]) -> None:
    """Batch-update the ``order`` field of multiple stages in one call.

    Args:
        stage_orders: List of ``{"stage_id": str, "order": int}`` dicts.
            Stages not listed are left unchanged.
    """
    for item in stage_orders:
        doc = await get_stage_config(item["stage_id"])
        if doc is not None:
            await doc.update({"$set": {"order": item["order"], "updated_at": _now()}})


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline Runs
# ─────────────────────────────────────────────────────────────────────────────


async def create_pipeline_run(
    run_id: str,
    document_name: str,
    document_path: str,
    llm_profile_id: Optional[str] = None,
) -> PipelineRunDocument:
    """Create a new pipeline run in ``PENDING`` state.

    Args:
        run_id: Caller-supplied UUID string (typically ``str(uuid.uuid4())``).
        document_name: Original filename of the uploaded requirements document.
        document_path: Absolute path to the saved file on disk.
        llm_profile_id: Optional ObjectId string of an :class:`LLMProfileDocument`
            to use as the LLM override for this run.  ``None`` means use the
            global default profile.

    Returns:
        The newly-created :class:`~app.db.models.PipelineRunDocument`.
    """
    doc = PipelineRunDocument(
        run_id=run_id,
        document_name=document_name,
        document_path=document_path,
        llm_profile_id=llm_profile_id,
        status=PipelineStatus.PENDING.value,
        agent_statuses={},
        completed_stages=[],
        stage_results_summary={},
    )
    await doc.insert()
    return doc


async def get_pipeline_run(run_id: str) -> Optional[PipelineRunDocument]:
    """Get a pipeline run by its UUID ``run_id``.

    Args:
        run_id: UUID string used as the logical primary key.

    Returns:
        The matching document or ``None``.
    """
    return await PipelineRunDocument.find_one(PipelineRunDocument.run_id == run_id)


async def get_all_pipeline_runs(
    skip: int = 0,
    limit: int = 20,
    status: Optional[str] = None,
) -> tuple[list[PipelineRunDocument], int]:
    """Return a paginated list of pipeline runs (newest first) and total count.

    Args:
        skip: Number of documents to skip.
        limit: Maximum number of documents to return.
        status: If provided, filter by this status value
            (e.g. ``"running"``, ``"completed"``).

    Returns:
        ``(items, total)`` where *total* is the count before pagination.
    """
    if status:
        query = PipelineRunDocument.find(PipelineRunDocument.status == status)
    else:
        query = PipelineRunDocument.find_all()

    total = await query.count()
    items = await query.sort("-created_at").skip(skip).limit(limit).to_list()
    return items, total


async def update_pipeline_status(
    run_id: str,
    status: str,
    **kwargs: Any,
) -> Optional[PipelineRunDocument]:
    """Update the status (and any extra fields) of a pipeline run.

    Terminal status values (``completed``, ``failed``, ``cancelled``)
    automatically set ``finished_at`` to the current UTC time unless the
    caller explicitly provides ``finished_at`` in *kwargs*.

    Args:
        run_id: UUID string of the pipeline run.
        status: New status string from :class:`~app.schemas.pipeline.PipelineStatus`.
        **kwargs: Additional fields to set atomically (e.g. ``error``,
            ``current_stage``, ``completed_stages``).

    Returns:
        The refreshed document, or ``None`` if *run_id* does not exist.
    """
    doc = await get_pipeline_run(run_id)
    if doc is None:
        return None

    update_data: dict[str, Any] = {"status": status, **kwargs}

    terminal_statuses = {
        PipelineStatus.COMPLETED.value,
        PipelineStatus.FAILED.value,
        PipelineStatus.CANCELLED.value,
    }
    if status in terminal_statuses and "finished_at" not in update_data:
        update_data["finished_at"] = _now()

    await doc.update({"$set": update_data})
    await doc.sync()
    return doc


async def update_agent_status(
    run_id: str,
    agent_id: str,
    status: str,
) -> Optional[PipelineRunDocument]:
    """Update the status of a single agent within a pipeline run.

    Uses a targeted ``$set`` on the dot-notation path
    ``agent_statuses.<agent_id>`` to avoid a read-modify-write race when
    multiple agents update their status concurrently.

    Args:
        run_id: UUID string of the pipeline run.
        agent_id: Agent slug whose status should be updated.
        status: New agent status (see :class:`~app.schemas.pipeline.AgentRunStatus`).

    Returns:
        The refreshed document, or ``None`` if *run_id* does not exist.
    """
    doc = await get_pipeline_run(run_id)
    if doc is None:
        return None
    await doc.update({"$set": {f"agent_statuses.{agent_id}": status}})
    await doc.sync()
    return doc


async def bulk_init_agent_statuses(
    run_id: str,
    agent_ids: list[str],
) -> Optional[PipelineRunDocument]:
    """Initialise all agent statuses to ``WAITING`` in one write.

    Call this immediately after creating the run and before starting
    execution so that the frontend can display a complete agent list
    with ``pending`` badges from the very beginning.

    Args:
        run_id: UUID string of the pipeline run.
        agent_ids: All agent slugs that will participate in the run.

    Returns:
        The refreshed document, or ``None`` if *run_id* does not exist.
    """
    doc = await get_pipeline_run(run_id)
    if doc is None:
        return None
    statuses = {agent_id: AgentRunStatus.WAITING.value for agent_id in agent_ids}
    await doc.update({"$set": {"agent_statuses": statuses}})
    await doc.sync()
    return doc


async def delete_pipeline_run(run_id: str) -> bool:
    """Delete a pipeline run and all of its associated result documents.

    Args:
        run_id: UUID string of the pipeline run to delete.

    Returns:
        ``True`` if the run was found and deleted; ``False`` otherwise.
    """
    doc = await get_pipeline_run(run_id)
    if doc is None:
        return False

    # Delete all result documents for this run first
    await PipelineResultDocument.find(PipelineResultDocument.run_id == run_id).delete()

    await doc.delete()
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline Results
# ─────────────────────────────────────────────────────────────────────────────


async def save_pipeline_result(
    run_id: str,
    stage: str,
    agent_id: str,
    output: Any,
) -> PipelineResultDocument:
    """Persist the output of a single agent/stage.

    The *output* value is stored as-is as native BSON — no ``json.dumps``
    needed.  Dicts, lists, strings, and numbers are all valid.

    Args:
        run_id: UUID string of the parent pipeline run.
        stage: Stage identifier (``"testcase"``, ``"execution"``, etc.).
        agent_id: Agent slug that produced this output.
        output: The raw output to store (any JSON-serialisable value).

    Returns:
        The newly-inserted :class:`~app.db.models.PipelineResultDocument`.
    """
    doc = PipelineResultDocument(
        run_id=run_id,
        stage=stage,
        agent_id=agent_id,
        output=output,
    )
    await doc.insert()
    return doc


async def get_pipeline_results(
    run_id: str,
    stage: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> list[PipelineResultDocument]:
    """Get all results for a run, optionally narrowed by stage and/or agent.

    Results are returned in ascending ``created_at`` order (oldest first),
    matching the execution timeline.

    Args:
        run_id: UUID string of the parent pipeline run.
        stage: If provided, only return results from this stage.
        agent_id: If provided, only return results from this agent.

    Returns:
        List of matching result documents.
    """
    filters: list[Any] = [PipelineResultDocument.run_id == run_id]
    if stage:
        filters.append(PipelineResultDocument.stage == stage)
    if agent_id:
        filters.append(PipelineResultDocument.agent_id == agent_id)
    return await PipelineResultDocument.find(*filters).sort("+created_at").to_list()


async def get_stage_results(
    run_id: str,
    stage: str,
) -> list[PipelineResultDocument]:
    """Get all result documents for a specific stage within a run.

    Convenience wrapper around :func:`get_pipeline_results`.

    Args:
        run_id: UUID string of the parent pipeline run.
        stage: Stage identifier.

    Returns:
        List of result documents for that stage, oldest first.
    """
    return await PipelineResultDocument.find(
        PipelineResultDocument.run_id == run_id,
        PipelineResultDocument.stage == stage,
    ).to_list()


async def get_latest_agent_result(
    run_id: str,
    agent_id: str,
) -> Optional[PipelineResultDocument]:
    """Get the most recent result document for a specific agent in a run.

    Useful when an agent may have been retried and you only need the last
    successful (or failed) output.

    Args:
        run_id: UUID string of the parent pipeline run.
        agent_id: Agent slug.

    Returns:
        The most recent result document, or ``None`` if none exist.
    """
    results = await (
        PipelineResultDocument.find(
            PipelineResultDocument.run_id == run_id,
            PipelineResultDocument.agent_id == agent_id,
        )
        .sort("-created_at")
        .limit(1)
        .to_list()
    )
    return results[0] if results else None
