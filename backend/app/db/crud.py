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
    PipelineTemplateDocument,
    StageConfigDocument,
)
from app.schemas.pipeline import AgentRunStatus, PipelineStatus
from app.schemas.stage_config import StageConfigCreate, StageConfigUpdate

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


async def count_agents_by_stage(stage: str) -> int:
    """Count enabled agents belonging to a specific stage.

    Args:
        stage: The stage_id to count agents for.

    Returns:
        Number of enabled agents in that stage.
    """
    return await AgentConfigDocument.find(
        AgentConfigDocument.stage == stage,
        AgentConfigDocument.enabled == True,  # noqa: E712
    ).count()


async def reassign_agents_stage(from_stage: str, to_stage: str) -> int:
    """Move all agents from one stage to another.

    Args:
        from_stage: Source stage_id.
        to_stage: Destination stage_id.

    Returns:
        Number of agents affected.
    """
    result = await AgentConfigDocument.find(
        AgentConfigDocument.stage == from_stage,
    ).update_many({"$set": {"stage": to_stage, "updated_at": _now()}})
    return result.modified_count if result is not None else 0  # type: ignore[union-attr]


async def get_stage_config(
    stage_id: str,
    template_id: Optional[str] = None,
) -> Optional[StageConfigDocument]:
    """Get a stage config by its ``stage_id``, optionally scoped to a pipeline template.

    Args:
        stage_id: Stage identifier such as ``"testcase"`` or ``"reporting"``.
        template_id: When provided, the lookup is scoped to this pipeline template
                     (pipeline-specific stages).  When ``None``, only global
                     stages (``template_id IS NULL``) are searched.

    Returns:
        The matching document or ``None``.
    """
    if template_id is not None:
        return await StageConfigDocument.find_one(
            StageConfigDocument.stage_id == stage_id,
            StageConfigDocument.template_id == template_id,
        )
    # Global stage lookup — match only documents without a template_id
    return await StageConfigDocument.find_one(
        StageConfigDocument.stage_id == stage_id,
        StageConfigDocument.template_id == None,  # noqa: E711
    )


async def get_all_stage_configs(
    enabled_only: bool = False,
    template_id: Optional[str] = None,
    no_fallback: bool = False,
) -> list[StageConfigDocument]:
    """Get all stage configs sorted by ``order`` ascending.

    Args:
        enabled_only: When ``True``, exclude stages where ``enabled=False``.
        template_id: When provided, first tries to return stages belonging to
                     this pipeline template.  If none exist yet, falls back to
                     global stages (``template_id IS NULL``) so that new
                     pipelines always have a working default set.
                     When ``None`` (default), all stages are returned.
        no_fallback: When ``True`` and ``template_id`` is provided, skip the
                     global-stage fallback and return an empty list if no
                     pipeline-specific stages exist.

    Returns:
        List of :class:`~app.db.models.StageConfigDocument` in execution order.
    """
    enabled_filter = (
        [StageConfigDocument.enabled == True]  # noqa: E712
        if enabled_only
        else []
    )

    if template_id is not None:
        # Try pipeline-specific stages first
        pipeline_stages = (
            await StageConfigDocument.find(
                StageConfigDocument.template_id == template_id,
                *enabled_filter,
            )
            .sort("+order")
            .to_list()
        )

        if pipeline_stages:
            return pipeline_stages

        if no_fallback:
            return []  # skip fallback when caller says so

        # No pipeline-specific stages → fall back to global stages
        return (
            await StageConfigDocument.find(
                StageConfigDocument.template_id == None,  # noqa: E711
                *enabled_filter,
            )
            .sort("+order")
            .to_list()
        )

    # No template_id filter — return everything
    if enabled_filter:
        return await StageConfigDocument.find(*enabled_filter).sort("+order").to_list()
    return await StageConfigDocument.find_all().sort("+order").to_list()


async def create_stage_config(data: StageConfigCreate) -> StageConfigDocument:
    """Create a new custom stage config (``is_builtin=False``).

    Args:
        data: Validated :class:`~app.schemas.stage_config.StageConfigCreate` payload.

    Returns:
        The newly-inserted document.
    """
    doc = StageConfigDocument(
        stage_id=data.stage_id,
        display_name=data.display_name,
        description=data.description,
        order=data.order,
        color=data.color,
        icon=data.icon,
        enabled=data.enabled,
        is_builtin=False,
        template_id=data.template_id,
    )
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
    data: StageConfigUpdate,
) -> Optional[StageConfigDocument]:
    """Partially update a stage config.

    Args:
        stage_id: Stage identifier to update.
        data: Validated :class:`~app.schemas.stage_config.StageConfigUpdate` payload.
              Only fields that are explicitly set are updated.

    Returns:
        The refreshed document, or ``None`` if *stage_id* does not exist.
    """
    doc = await get_stage_config(stage_id)
    if doc is None:
        return None
    update_data = data.model_dump(exclude_unset=True)
    update_data["updated_at"] = _now()
    await doc.update({"$set": update_data})
    await doc.sync()
    return doc


async def delete_stage_config(stage_id: str) -> bool:
    """Delete a stage config by stage_id.

    The caller (router) is responsible for checking ``is_builtin`` before
    calling this function.

    Args:
        stage_id: Stage identifier to delete.

    Returns:
        ``True`` if the document was deleted, ``False`` if not found.
    """
    doc = await get_stage_config(stage_id)
    if doc is None:
        return False
    await doc.delete()
    return True


async def reorder_stages(stage_ids: list[str]) -> list[StageConfigDocument]:
    """Reorder stages by updating their ``order`` field.

    The position of each ``stage_id`` in the list determines its new order
    value (``index * 100``).

    Args:
        stage_ids: Ordered list of stage_ids.

    Returns:
        Full updated list of all stage configs, sorted by new order.
    """
    for idx, stage_id in enumerate(stage_ids):
        doc = await get_stage_config(stage_id)
        if doc is not None:
            await doc.update({"$set": {"order": idx * 100, "updated_at": _now()}})
    return await get_all_stage_configs()


async def get_stage_configs_for_template(
    template_id: str,
) -> list[StageConfigDocument]:
    """Convenience wrapper — return all stage configs for a specific pipeline template.

    Args:
        template_id: The pipeline template whose stages should be returned.

    Returns:
        List of :class:`~app.db.models.StageConfigDocument` sorted by ``order``.
    """
    return await get_all_stage_configs(template_id=template_id)


async def get_agents_by_pipeline():
    """Return agents grouped by pipeline template → stage.

    For every pipeline template in the DB the function:

    1. Fetches stage configs that belong to that template (by ``template_id``).
    2. Iterates over DAG nodes whose ``node_type`` is ``"agent"`` or
       ``"pure_python"`` and resolves the backing
       :class:`~app.db.models.AgentConfigDocument`.
    3. Slots each resolved agent into its node's ``stage_id`` bucket (or
       ``"__unassigned__"`` when the node has no stage).
    4. Appends an *Unassigned* bucket at the end when there are any such agents.

    Returns:
        :class:`~app.schemas.agent_config.AgentConfigByPipelineResponse`
    """
    from app.schemas.agent_config import (
        AgentConfigByPipelineResponse,
        AgentConfigSummary,
        PipelineAgentGroup,
        PipelineStageEntry,
    )

    templates = await PipelineTemplateDocument.find_all().sort("+created_at").to_list()
    all_agents = await AgentConfigDocument.find_all().to_list()
    agent_map = {a.agent_id: a for a in all_agents}

    pipelines: list[PipelineAgentGroup] = []
    total_agents = 0

    for template in templates:
        # Only load stages that belong specifically to this pipeline template.
        # No fallback to global stages — pipelines without configured stages
        # show all their agents in the "__unassigned__" bucket.
        pipeline_stages = (
            await StageConfigDocument.find(
                StageConfigDocument.template_id == template.template_id
            )
            .sort("+order")
            .to_list()
        )

        # Build per-stage agent buckets
        stage_map: dict[str, list[AgentConfigSummary]] = {
            s.stage_id: [] for s in pipeline_stages
        }
        stage_map["__unassigned__"] = []

        # Walk DAG nodes and slot resolved agents into their stage bucket
        for node in template.nodes:
            if node.node_type not in ("agent", "pure_python"):
                continue
            if not node.agent_id:
                continue
            agent_doc = agent_map.get(node.agent_id)
            if not agent_doc:
                continue

            summary = AgentConfigSummary(
                id=str(agent_doc.id),
                agent_id=agent_doc.agent_id,
                display_name=agent_doc.display_name,
                stage=agent_doc.stage,
                llm_profile_id=agent_doc.llm_profile_id,
                llm_profile_name=None,
                enabled=agent_doc.enabled,
                verbose=agent_doc.verbose,
                max_iter=agent_doc.max_iter,
                is_custom=agent_doc.is_custom,
                updated_at=agent_doc.updated_at,
                node_id=node.node_id,
            )

            node_stage_id = node.stage_id or "__unassigned__"
            if node_stage_id not in stage_map:
                stage_map.setdefault(node_stage_id, [])
            stage_map[node_stage_id].append(summary)

        # Build ordered stage entries from the pipeline's stage configs
        stage_entries: list[PipelineStageEntry] = []
        for stage in pipeline_stages:
            stage_entries.append(
                PipelineStageEntry(
                    stage_id=stage.stage_id,
                    display_name=stage.display_name,
                    description=stage.description,
                    order=stage.order,
                    color=stage.color,
                    icon=stage.icon,
                    is_builtin=stage.is_builtin,
                    agents=stage_map.get(stage.stage_id, []),
                )
            )

        # Append the unassigned bucket only when it contains agents
        unassigned = stage_map.get("__unassigned__", [])
        if unassigned:
            stage_entries.append(
                PipelineStageEntry(
                    stage_id="__unassigned__",
                    display_name="Unassigned",
                    description="Agents not yet assigned to a stage",
                    order=9999,
                    color="#3d5070",
                    icon=None,
                    is_builtin=False,
                    agents=unassigned,
                )
            )

        pipeline_agent_count = sum(len(s.agents) for s in stage_entries)
        total_agents += pipeline_agent_count

        pipelines.append(
            PipelineAgentGroup(
                template_id=template.template_id,
                name=template.name,
                description=template.description,
                stages=stage_entries,
                total_agents=pipeline_agent_count,
            )
        )

    return AgentConfigByPipelineResponse(pipelines=pipelines, total_agents=total_agents)


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
    template_id: Optional[str] = None,
) -> tuple[list[PipelineRunDocument], int]:
    """Return a paginated list of pipeline runs (newest first) and total count.

    Args:
        skip: Number of documents to skip.
        limit: Maximum number of documents to return.
        status: If provided, filter by this status value
            (e.g. ``"running"``, ``"completed"``).
        template_id: If provided, filter runs belonging to this template.

    Returns:
        ``(items, total)`` where *total* is the count before pagination.
    """
    conditions = []
    if status:
        conditions.append(PipelineRunDocument.status == status)
    if template_id:
        conditions.append(PipelineRunDocument.template_id == template_id)

    if conditions:
        query = PipelineRunDocument.find(*conditions)
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


async def get_pipeline_result_by_node(
    run_id: str,
    node_id: str,
) -> Optional[PipelineResultDocument]:
    """Get a single pipeline result by run_id and node_id.

    Args:
        run_id: UUID string of the parent pipeline run.
        node_id: DAG node ID whose result to retrieve.

    Returns:
        The matching :class:`~app.db.models.PipelineResultDocument`, or
        ``None`` if no result exists for this node/run combination.
    """
    return await PipelineResultDocument.find_one(
        PipelineResultDocument.run_id == run_id,
        PipelineResultDocument.node_id == node_id,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Startup Recovery
# ─────────────────────────────────────────────────────────────────────────────


async def recover_orphaned_runs() -> int:
    """Mark any pipeline run stuck in ``running`` or ``pending`` as ``failed``.

    Called once on application startup to clean up runs that were in-progress
    when the server was last shut down or crashed unexpectedly.

    A run is considered "orphaned" if it has ``status="running"`` or
    ``status="pending"`` — meaning it was started but never reached a terminal
    state before the process exited.

    Returns:
        The number of runs that were recovered (transitioned to ``failed``).
    """
    _stale = {"running", "pending"}
    stale_runs = await PipelineRunDocument.find(
        {"status": {"$in": list(_stale)}}
    ).to_list()

    count = 0
    for run in stale_runs:
        run.status = PipelineStatus.FAILED.value
        run.error = (
            "Server restarted while this pipeline was active. "
            "The run was automatically marked as failed."
        )
        run.finished_at = _now()
        await run.save()
        logger.warning(
            "[CRUD] Recovered orphaned run  run_id=%r  old_status=%r",
            run.run_id,
            _stale,
        )
        count += 1

    return count


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline Templates  (V3 NEW)
# ─────────────────────────────────────────────────────────────────────────────


async def get_pipeline_template(
    template_id: str,
) -> Optional[PipelineTemplateDocument]:
    """Get a pipeline template by its unique ``template_id`` slug.

    Args:
        template_id: The URL-safe slug identifier (e.g. ``"auto-testing"``).

    Returns:
        The matching :class:`~app.db.models.PipelineTemplateDocument`, or
        ``None`` if not found.
    """
    return await PipelineTemplateDocument.find_one(
        PipelineTemplateDocument.template_id == template_id
    )


async def get_all_pipeline_templates(
    include_archived: bool = False,
    tag: Optional[str] = None,
) -> list[PipelineTemplateDocument]:
    """Return all pipeline templates, sorted by updated_at descending.

    Args:
        include_archived: When ``True``, include archived templates.
        tag: Optional tag to filter by (exact match).

    Returns:
        List of :class:`~app.db.models.PipelineTemplateDocument`.
    """
    conditions = []
    if not include_archived:
        conditions.append(PipelineTemplateDocument.is_archived == False)  # noqa: E712
    if tag:
        conditions.append(PipelineTemplateDocument.tags == tag)

    if conditions:
        query = PipelineTemplateDocument.find(*conditions)
    else:
        query = PipelineTemplateDocument.find_all()

    return await query.sort("-updated_at").to_list()


async def create_pipeline_template(
    data: dict,  # type: ignore[type-arg]
) -> PipelineTemplateDocument:
    """Create a new pipeline template document.

    Args:
        data: Dict matching the :class:`~app.db.models.PipelineTemplateDocument`
            schema.  ``template_id`` must be unique.

    Returns:
        The newly-created :class:`~app.db.models.PipelineTemplateDocument`.
    """
    from app.db.models import PipelineEdgeConfig, PipelineNodeConfig

    # Ensure nodes and edges are the correct embedded types
    nodes_data = data.pop("nodes", [])
    edges_data = data.pop("edges", [])
    nodes = [PipelineNodeConfig(**n) if isinstance(n, dict) else n for n in nodes_data]
    edges = [PipelineEdgeConfig(**e) if isinstance(e, dict) else e for e in edges_data]

    doc = PipelineTemplateDocument(
        **data,
        nodes=nodes,
        edges=edges,
        created_at=_now(),
        updated_at=_now(),
    )
    await doc.insert()
    logger.info("Created pipeline template: %s", doc.template_id)
    return doc


async def update_pipeline_template(
    template_id: str,
    update_data: dict,  # type: ignore[type-arg]
) -> Optional[PipelineTemplateDocument]:
    """Update a pipeline template and auto-increment version.

    Args:
        template_id: The slug of the template to update.
        update_data: Dict of fields to update.  Only provided keys are changed.
            If ``nodes`` or ``edges`` are provided they must be dicts or
            ``PipelineNodeConfig`` / ``PipelineEdgeConfig`` objects.

    Returns:
        The refreshed document, or ``None`` if *template_id* does not exist.
    """
    from app.db.models import PipelineEdgeConfig, PipelineNodeConfig

    doc = await get_pipeline_template(template_id)
    if doc is None:
        return None

    # Handle nodes / edges if provided (convert dicts → embedded models)
    if "nodes" in update_data:
        raw = update_data.pop("nodes")
        update_data["nodes"] = [
            PipelineNodeConfig(**n) if isinstance(n, dict) else n for n in raw
        ]
    if "edges" in update_data:
        raw = update_data.pop("edges")
        update_data["edges"] = [
            PipelineEdgeConfig(**e) if isinstance(e, dict) else e for e in raw
        ]

    # Auto-increment version whenever the template content changes
    update_data["version"] = doc.version + 1
    update_data["updated_at"] = _now()

    for key, value in update_data.items():
        setattr(doc, key, value)

    await doc.save()
    logger.info("Updated pipeline template: %s (version %d)", template_id, doc.version)
    return doc


async def delete_pipeline_template(template_id: str) -> bool:
    """Hard-delete a pipeline template.

    Should only be called after confirming there are no runs for this template.
    Built-in templates should be archived instead.

    Args:
        template_id: Slug of the template to delete.

    Returns:
        ``True`` if deleted, ``False`` if not found.
    """
    doc = await get_pipeline_template(template_id)
    if doc is None:
        return False
    await doc.delete()
    logger.info("Deleted pipeline template: %s", template_id)
    return True


async def clone_pipeline_template(
    original: PipelineTemplateDocument,
    new_template_id: str,
    new_name: str,
) -> PipelineTemplateDocument:
    """Clone an existing pipeline template into a new one.

    The cloned template starts at version 1, is not built-in, and is not archived.

    Args:
        original: The source template document.
        new_template_id: URL-safe slug for the new template.
        new_name: Display name for the new template.

    Returns:
        The newly-created cloned :class:`~app.db.models.PipelineTemplateDocument`.
    """
    clone_data = {
        "template_id": new_template_id,
        "name": new_name,
        "description": original.description,
        "version": 1,
        "nodes": [n.model_dump() for n in original.nodes],
        "edges": [e.model_dump() for e in original.edges],
        "is_builtin": False,
        "is_archived": False,
        "tags": list(original.tags),
    }
    cloned = await create_pipeline_template(clone_data)
    logger.info("Cloned template '%s' → '%s'", original.template_id, new_template_id)
    return cloned


async def count_runs_for_template(template_id: str) -> int:
    """Return the number of pipeline runs associated with a template.

    Used before deletion to enforce the "no runs" constraint.

    Args:
        template_id: The slug of the template.

    Returns:
        Integer count of matching :class:`~app.db.models.PipelineRunDocument`
        records.
    """
    return await PipelineRunDocument.find(
        PipelineRunDocument.template_id == template_id
    ).count()


async def get_latest_run_for_template(
    template_id: str,
) -> Optional[PipelineRunDocument]:
    """Return the most recently created run for a given template.

    Used by the template list endpoint to show the last-run status badge.

    Args:
        template_id: The slug of the template.

    Returns:
        The most recent :class:`~app.db.models.PipelineRunDocument`, or
        ``None`` if no runs exist.
    """
    results = (
        await PipelineRunDocument.find(PipelineRunDocument.template_id == template_id)
        .sort("-created_at")
        .limit(1)
        .to_list()
    )
    return results[0] if results else None


async def update_node_stage(
    template_id: str,
    node_id: str,
    stage_id: Optional[str],
) -> Optional[PipelineTemplateDocument]:
    """Set (or clear) the stage_id on a specific node within a pipeline template.

    Args:
        template_id: The pipeline template's slug.
        node_id:     The node's unique slug within the template.
        stage_id:    The new stage_id to assign, or ``None`` to unassign.

    Returns:
        The updated template document, or ``None`` if not found.
    """
    template = await PipelineTemplateDocument.find_one(
        PipelineTemplateDocument.template_id == template_id
    )
    if template is None:
        return None

    matched = False
    for node in template.nodes:
        if node.node_id == node_id:
            node.stage_id = stage_id
            matched = True
            break

    if not matched:
        return None

    template.updated_at = _now()
    await template.save()
    return template


# ─────────────────────────────────────────────────────────────────────────────
# V3 DAG Pipeline Run helpers
# ─────────────────────────────────────────────────────────────────────────────


async def update_pipeline_run(
    run_id: str,
    **kwargs: Any,
) -> Optional[PipelineRunDocument]:
    """V3 flexible pipeline run updater.

    Supports atomic per-node status updates via MongoDB dot-notation paths.
    Terminal statuses (completed/failed/cancelled) auto-set completed_at/finished_at.

    Args:
        run_id: UUID string of the pipeline run.
        **kwargs: Fields to update. Special key: ``node_statuses`` (dict[str,str])
            triggers dot-notation $set per node (e.g. ``node_statuses.agent_a = "running"``).

    Returns:
        The refreshed document, or None if run_id does not exist.
    """
    doc = await get_pipeline_run(run_id)
    if doc is None:
        return None

    set_ops: dict[str, Any] = {}

    # Special: node_statuses → atomic per-node update with dot-notation
    if "node_statuses" in kwargs:
        node_statuses: dict[str, str] = kwargs.pop("node_statuses")
        for nid, nstatus in node_statuses.items():
            set_ops[f"node_statuses.{nid}"] = nstatus

    # Auto-set terminal timestamps
    status = kwargs.get("status")
    if status in {
        PipelineStatus.COMPLETED.value,
        PipelineStatus.FAILED.value,
        PipelineStatus.CANCELLED.value,
    }:
        kwargs.setdefault("completed_at", _now())
        kwargs.setdefault("finished_at", _now())

    set_ops.update(kwargs)

    if set_ops:
        await doc.update({"$set": set_ops})
        await doc.sync()

    logger.debug("Updated pipeline run: %s  fields=%s", run_id, list(set_ops.keys()))
    return doc


async def save_node_result(
    run_id: str,
    node_id: str,
    status: str = "completed",
    agent_id: Optional[str] = None,
    output: Any = None,
    input_data: Optional[dict] = None,  # type: ignore[type-arg]
    error_message: Optional[str] = None,
    duration_seconds: Optional[float] = None,
) -> PipelineResultDocument:
    """Persist the output of a single DAG node execution (V3).

    Args:
        run_id: UUID string of the parent pipeline run.
        node_id: DAG node_id that produced this result.
        status: "completed" | "failed" | "skipped".
        agent_id: Agent config slug used by this node (if AGENT type).
        output: The raw output value (any JSON-serialisable value).
        input_data: What the node received as input (for debugging/replay).
        error_message: Error string if status="failed".
        duration_seconds: Execution time in seconds.

    Returns:
        The newly-inserted PipelineResultDocument.
    """
    now = _now()
    doc = PipelineResultDocument(
        run_id=run_id,
        node_id=node_id,
        agent_id=agent_id,
        stage=node_id,  # V2 compat alias
        result_type="node_output",
        output=output,
        input_data=input_data or {},
        status=status,
        error_message=error_message,
        duration_seconds=duration_seconds,
        completed_at=now if status in ("completed", "failed") else None,
    )
    await doc.insert()
    logger.info(
        "Saved node result: run_id=%s node_id=%s status=%s", run_id, node_id, status
    )
    return doc


async def create_dag_run(
    run_id: str,
    template_id: str,
    template_snapshot: dict,  # type: ignore[type-arg]
    document_name: str = "",
    file_path: Optional[str] = None,
    llm_profile_id: Optional[str] = None,
    run_params: Optional[dict] = None,  # type: ignore[type-arg]
) -> PipelineRunDocument:
    """Create a new V3 DAG pipeline run in PENDING state.

    Args:
        run_id: Caller-supplied UUID string.
        template_id: Slug of the pipeline template to run.
        template_snapshot: Snapshot of template nodes+edges at run time.
        document_name: Original filename of uploaded document (if any).
        file_path: Absolute path to uploaded file (if any).
        llm_profile_id: Optional LLM profile override.
        run_params: Extra run parameters dict.

    Returns:
        The newly-created PipelineRunDocument.
    """
    doc = PipelineRunDocument(
        run_id=run_id,
        template_id=template_id,
        template_snapshot=template_snapshot,
        document_name=document_name,
        document_path=file_path,
        file_path=file_path,
        llm_profile_id=llm_profile_id,
        run_params=run_params or {},
        status=PipelineStatus.PENDING.value,
        agent_statuses={},
        completed_stages=[],
        stage_results_summary={},
    )
    await doc.insert()
    logger.info("Created DAG run: %s for template: %s", run_id, template_id)
    return doc
