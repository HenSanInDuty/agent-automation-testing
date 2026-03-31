from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.db.models import AgentConfig, LLMProfile, PipelineResult, PipelineRun
from app.schemas.agent_config import AgentConfigUpdate
from app.schemas.llm_profile import LLMProfileCreate, LLMProfileUpdate
from app.schemas.pipeline import AgentRunStatus, PipelineStatus
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# LLMProfile CRUD
# ─────────────────────────────────────────────────────────────────────────────


def get_llm_profile(db: Session, profile_id: int) -> Optional[LLMProfile]:
    """Get a single LLM profile by primary key."""
    return db.get(LLMProfile, profile_id)


def get_llm_profile_by_name(db: Session, name: str) -> Optional[LLMProfile]:
    """Get a single LLM profile by its unique name."""
    stmt = select(LLMProfile).where(LLMProfile.name == name)
    return db.scalar(stmt)


def get_all_llm_profiles(
    db: Session,
    skip: int = 0,
    limit: int = 100,
) -> tuple[list[LLMProfile], int]:
    """
    Returns a page of LLM profiles and the total count.

    Returns:
        (items, total)
    """
    count_stmt = select(func.count()).select_from(LLMProfile)
    total: int = db.scalar(count_stmt) or 0

    stmt = select(LLMProfile).order_by(LLMProfile.id).offset(skip).limit(limit)
    items = list(db.scalars(stmt).all())

    return items, total


def get_default_llm_profile(db: Session) -> Optional[LLMProfile]:
    """Return the profile marked as is_default=True, or None if none is set."""
    stmt = select(LLMProfile).where(LLMProfile.is_default.is_(True)).limit(1)
    return db.scalar(stmt)


def create_llm_profile(db: Session, payload: LLMProfileCreate) -> LLMProfile:
    """
    Insert a new LLM profile.
    If is_default=True, clears the default flag on all other profiles first.
    """
    if payload.is_default:
        _clear_default_profiles(db)

    profile = LLMProfile(
        name=payload.name,
        provider=payload.provider.value,
        model=payload.model,
        api_key=payload.api_key,
        base_url=payload.base_url,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        is_default=payload.is_default,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def update_llm_profile(
    db: Session,
    profile_id: int,
    payload: LLMProfileUpdate,
) -> Optional[LLMProfile]:
    """
    Partial update of an LLM profile.
    Only fields explicitly set in the payload are written.
    Returns None if the profile does not exist.
    """
    profile = get_llm_profile(db, profile_id)
    if profile is None:
        return None

    update_data = payload.model_dump(exclude_unset=True)

    if update_data.get("is_default") is True:
        _clear_default_profiles(db, exclude_id=profile_id)

    # Normalise enum → string value
    if "provider" in update_data and hasattr(update_data["provider"], "value"):
        update_data["provider"] = update_data["provider"].value

    for field, value in update_data.items():
        setattr(profile, field, value)

    profile.updated_at = _now()
    db.commit()
    db.refresh(profile)
    return profile


def delete_llm_profile(db: Session, profile_id: int) -> bool:
    """
    Delete an LLM profile by ID.
    Returns True if deleted, False if not found.
    """
    profile = get_llm_profile(db, profile_id)
    if profile is None:
        return False

    db.delete(profile)
    db.commit()
    return True


def set_default_llm_profile(db: Session, profile_id: int) -> Optional[LLMProfile]:
    """
    Mark the given profile as default and unset all others.
    Returns the updated profile, or None if not found.
    """
    profile = get_llm_profile(db, profile_id)
    if profile is None:
        return None

    _clear_default_profiles(db, exclude_id=profile_id)
    profile.is_default = True
    profile.updated_at = _now()
    db.commit()
    db.refresh(profile)
    return profile


def _clear_default_profiles(db: Session, exclude_id: Optional[int] = None) -> None:
    """Set is_default=False for all profiles (optionally excluding one ID)."""
    stmt = update(LLMProfile).values(is_default=False, updated_at=_now())
    if exclude_id is not None:
        stmt = stmt.where(LLMProfile.id != exclude_id)
    db.execute(stmt)


# ─────────────────────────────────────────────────────────────────────────────
# AgentConfig CRUD
# ─────────────────────────────────────────────────────────────────────────────


def get_agent_config(db: Session, agent_id: str) -> Optional[AgentConfig]:
    """Get a single agent config by its unique agent_id slug."""
    stmt = select(AgentConfig).where(AgentConfig.agent_id == agent_id)
    return db.scalar(stmt)


def get_agent_config_by_pk(db: Session, pk: int) -> Optional[AgentConfig]:
    """Get a single agent config by primary key."""
    return db.get(AgentConfig, pk)


def get_all_agent_configs(
    db: Session,
    stage: Optional[str] = None,
    enabled_only: bool = False,
) -> list[AgentConfig]:
    """
    Get all agent configs, optionally filtered by stage and/or enabled status.
    Returns in deterministic order: by stage then by id.
    """
    stmt = select(AgentConfig)

    if stage:
        stmt = stmt.where(AgentConfig.stage == stage)

    if enabled_only:
        stmt = stmt.where(AgentConfig.enabled.is_(True))

    stmt = stmt.order_by(AgentConfig.stage, AgentConfig.id)
    return list(db.scalars(stmt).all())


def update_agent_config(
    db: Session,
    agent_id: str,
    payload: AgentConfigUpdate,
) -> Optional[AgentConfig]:
    """
    Partial update of an agent config.
    Returns None if the agent_id does not exist.
    """
    config = get_agent_config(db, agent_id)
    if config is None:
        return None

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(config, field, value)

    config.updated_at = _now()
    db.commit()
    db.refresh(config)
    return config


def upsert_agent_config(db: Session, defaults: dict) -> AgentConfig:
    """
    Insert a new agent config or skip if agent_id already exists.
    Used by the seeder — does NOT overwrite user customisations.

    Args:
        defaults: dict matching AgentConfig column names.

    Returns:
        The existing or newly-created AgentConfig instance.
    """
    existing = get_agent_config(db, defaults["agent_id"])
    if existing is not None:
        return existing  # already seeded — leave user config intact

    config = AgentConfig(**defaults)
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def reset_agent_config(
    db: Session,
    agent_id: str,
    defaults: dict,
) -> Optional[AgentConfig]:
    """
    Reset an agent config back to its shipped defaults.
    Also clears the llm_profile_id (so it falls back to global default).

    Args:
        agent_id: The unique slug of the agent to reset.
        defaults: Dict of default field values from SEED_AGENT_CONFIGS.

    Returns:
        The updated AgentConfig, or None if not found.
    """
    config = get_agent_config(db, agent_id)
    if config is None:
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
    for field in resettable:
        if field in defaults:
            setattr(config, field, defaults[field])

    # Always clear per-agent LLM override on reset
    config.llm_profile_id = None
    config.updated_at = _now()
    db.commit()
    db.refresh(config)
    return config


def reset_all_agent_configs(
    db: Session,
    all_defaults: list[dict],
) -> list[AgentConfig]:
    """
    Reset every agent config to its shipped defaults.
    Clears all per-agent LLM overrides.

    Returns:
        List of all updated AgentConfig instances.
    """
    defaults_map = {d["agent_id"]: d for d in all_defaults}
    configs = get_all_agent_configs(db)

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

    for config in configs:
        defaults = defaults_map.get(config.agent_id)
        if defaults is None:
            continue
        for field in resettable:
            if field in defaults:
                setattr(config, field, defaults[field])
        config.llm_profile_id = None
        config.updated_at = _now()

    db.commit()
    for config in configs:
        db.refresh(config)

    return configs


# ─────────────────────────────────────────────────────────────────────────────
# PipelineRun CRUD
# ─────────────────────────────────────────────────────────────────────────────


def create_pipeline_run(
    db: Session,
    document_name: str,
    document_path: str,
    llm_profile_id: Optional[int] = None,
) -> PipelineRun:
    """Create a new pipeline run in PENDING state."""
    run = PipelineRun(
        id=str(uuid.uuid4()),
        document_name=document_name,
        document_path=document_path,
        llm_profile_id=llm_profile_id,
        status=PipelineStatus.PENDING.value,
        agent_statuses="{}",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def get_pipeline_run(db: Session, run_id: str) -> Optional[PipelineRun]:
    """Get a pipeline run by UUID."""
    return db.get(PipelineRun, run_id)


def get_all_pipeline_runs(
    db: Session,
    skip: int = 0,
    limit: int = 20,
    status: Optional[str] = None,
) -> tuple[list[PipelineRun], int]:
    """
    Returns a page of pipeline runs (newest first) and the total count.

    Returns:
        (items, total)
    """
    count_stmt = select(func.count()).select_from(PipelineRun)
    stmt = select(PipelineRun).order_by(PipelineRun.created_at.desc())

    if status:
        count_stmt = count_stmt.where(PipelineRun.status == status)
        stmt = stmt.where(PipelineRun.status == status)

    total: int = db.scalar(count_stmt) or 0
    items = list(db.scalars(stmt.offset(skip).limit(limit)).all())

    return items, total


def update_pipeline_run_status(
    db: Session,
    run_id: str,
    status: PipelineStatus,
    error: Optional[str] = None,
) -> Optional[PipelineRun]:
    """
    Update the top-level status of a pipeline run.
    Automatically sets finished_at when status is COMPLETED or FAILED.
    """
    run = get_pipeline_run(db, run_id)
    if run is None:
        return None

    run.status = status.value
    if error is not None:
        run.error = error
    if status in (PipelineStatus.COMPLETED, PipelineStatus.FAILED):
        run.finished_at = _now()

    db.commit()
    db.refresh(run)
    return run


def update_agent_status(
    db: Session,
    run_id: str,
    agent_id: str,
    status: AgentRunStatus,
) -> Optional[PipelineRun]:
    """
    Update the status of a single agent within a pipeline run.
    Thread-safe: re-reads agent_statuses JSON before writing.
    """
    run = get_pipeline_run(db, run_id)
    if run is None:
        return None

    run.set_agent_status(agent_id, status.value)
    db.commit()
    db.refresh(run)
    return run


def bulk_init_agent_statuses(
    db: Session,
    run_id: str,
    agent_ids: list[str],
) -> Optional[PipelineRun]:
    """
    Initialise all agent statuses to WAITING at once.
    Call this right after creating the run before execution starts.
    """
    run = get_pipeline_run(db, run_id)
    if run is None:
        return None

    statuses = {agent_id: AgentRunStatus.WAITING.value for agent_id in agent_ids}
    run.agent_statuses = json.dumps(statuses)
    db.commit()
    db.refresh(run)
    return run


def delete_pipeline_run(db: Session, run_id: str) -> bool:
    """
    Delete a pipeline run and all its results (cascade).
    Returns True if deleted, False if not found.
    """
    run = get_pipeline_run(db, run_id)
    if run is None:
        return False

    db.delete(run)
    db.commit()
    return True


# ─────────────────────────────────────────────────────────────────────────────
# PipelineResult CRUD
# ─────────────────────────────────────────────────────────────────────────────


def create_pipeline_result(
    db: Session,
    run_id: str,
    stage: str,
    agent_id: str,
    output: dict | list | str,
) -> PipelineResult:
    """
    Persist the output of a single agent.

    Args:
        output: Will be JSON-serialised if it is a dict or list.
    """
    output_str = (
        json.dumps(output, ensure_ascii=False)
        if isinstance(output, (dict, list))
        else str(output)
    )

    result = PipelineResult(
        run_id=run_id,
        stage=stage,
        agent_id=agent_id,
        output=output_str,
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    return result


def get_pipeline_results(
    db: Session,
    run_id: str,
    stage: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> list[PipelineResult]:
    """
    Get all results for a run, optionally filtered by stage and/or agent_id.
    Ordered by creation time ascending.
    """
    stmt = (
        select(PipelineResult)
        .where(PipelineResult.run_id == run_id)
        .order_by(PipelineResult.created_at)
    )

    if stage:
        stmt = stmt.where(PipelineResult.stage == stage)

    if agent_id:
        stmt = stmt.where(PipelineResult.agent_id == agent_id)

    return list(db.scalars(stmt).all())


def get_latest_agent_result(
    db: Session,
    run_id: str,
    agent_id: str,
) -> Optional[PipelineResult]:
    """Get the most recent result for a specific agent in a run."""
    stmt = (
        select(PipelineResult)
        .where(
            PipelineResult.run_id == run_id,
            PipelineResult.agent_id == agent_id,
        )
        .order_by(PipelineResult.created_at.desc())
        .limit(1)
    )
    return db.scalar(stmt)
