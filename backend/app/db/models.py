"""
db/models.py – Beanie Document models for MongoDB.

These replace the V1 SQLAlchemy ORM models.  Each Document IS a Pydantic
BaseModel — no separate schema layer is needed for internal operations.

Documents:
    LLMProfileDocument    – LLM provider/model profiles
    AgentConfigDocument   – CrewAI agent configurations
    StageConfigDocument   – Pipeline stage configurations
    PipelineRunDocument   – Pipeline run records (one per upload + run)
    PipelineResultDocument – Per-agent/per-stage output blobs
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from beanie import Document, Indexed
from pydantic import Field

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _now() -> datetime:
    """Return the current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# LLMProfileDocument
# ─────────────────────────────────────────────────────────────────────────────


class LLMProfileDocument(Document):
    """MongoDB document that stores one LLM provider/model profile.

    A profile encapsulates everything needed to instantiate a LiteLLM / CrewAI
    ``LLM`` object at runtime: provider name, model identifier, credentials,
    and generation hyper-parameters.

    Only one profile may have ``is_default=True`` at any given time; this
    constraint is enforced at the CRUD layer (see ``db/crud.py``).

    Attributes:
        name:         Human-readable unique identifier shown in the admin UI.
        provider:     LLM provider slug (openai | anthropic | ollama |
                      huggingface | azure_openai | groq).
        model:        Provider-specific model name, e.g. ``"gpt-4o"``.
        api_key:      Raw API key (may be encrypted at rest when
                      ``ENCRYPT_API_KEYS=True``).  Always masked in API
                      responses.
        base_url:     Custom inference endpoint URL (Ollama, Azure, LM Studio,
                      vLLM, etc.).
        temperature:  Sampling temperature in [0, 2].
        max_tokens:   Upper token budget per LLM call.
        is_default:   When ``True`` this profile is used for any agent that
                      has no per-agent override assigned.
        created_at:   UTC timestamp set once on insert.
        updated_at:   UTC timestamp refreshed on every update.
    """

    name: Indexed(str, unique=True)  # type: ignore[valid-type]
    provider: str  # openai | anthropic | ollama | huggingface | azure_openai | groq
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.1
    max_tokens: int = 2048
    is_default: bool = False
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    class Settings:
        """Beanie collection settings."""

        name = "llm_profiles"
        indexes = [
            "provider",
            [("is_default", 1)],
        ]


# ─────────────────────────────────────────────────────────────────────────────
# AgentConfigDocument
# ─────────────────────────────────────────────────────────────────────────────


class AgentConfigDocument(Document):
    """MongoDB document that stores the configuration for one CrewAI agent.

    Each of the 19 seeded agents has a unique ``agent_id`` slug that is used
    throughout the codebase to look up configurations at runtime.  Admins can
    customise ``role``, ``goal``, ``backstory``, ``max_iter``, and assign a
    per-agent LLM profile override through the admin UI.

    Attributes:
        agent_id:        Unique slug used in code, e.g. ``"requirement_analyzer"``.
        display_name:    Human-readable name shown in the admin UI.
        stage:           Pipeline stage this agent belongs to
                         (ingestion | testcase | execution | reporting).
        role:            CrewAI agent ``role`` prompt — short noun phrase
                         describing the agent's expertise.
        goal:            CrewAI agent ``goal`` prompt — what the agent is
                         trying to achieve in a single task.
        backstory:       CrewAI agent ``backstory`` prompt — personality and
                         expertise that shape the LLM's behaviour.
        llm_profile_id:  ObjectId string referencing a
                         :class:`LLMProfileDocument`.  ``None`` means "use
                         the global default profile".
        enabled:         When ``False`` the agent is skipped during pipeline
                         execution.
        verbose:         Pass ``verbose=True`` to the underlying CrewAI agent,
                         enabling detailed step logging.
        max_iter:        Maximum number of LLM reasoning iterations per task.
        is_custom:       ``True`` if the record was created by an admin via the
                         UI; ``False`` for the 19 seeded defaults.
        created_at:      UTC timestamp set once on insert.
        updated_at:      UTC timestamp refreshed on every update.
    """

    agent_id: Indexed(str, unique=True)  # type: ignore[valid-type]
    display_name: str
    stage: Indexed(str)  # type: ignore[valid-type]
    role: str
    goal: str
    backstory: str
    llm_profile_id: Optional[str] = None  # ObjectId string → ref to LLMProfileDocument
    enabled: bool = True
    verbose: bool = False
    max_iter: int = 5
    is_custom: bool = False  # True if user-created, False if seeded
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    class Settings:
        """Beanie collection settings."""

        name = "agent_configs"
        indexes = [
            "stage",
            [("stage", 1), ("enabled", 1)],
        ]


# ─────────────────────────────────────────────────────────────────────────────
# StageConfigDocument
# ─────────────────────────────────────────────────────────────────────────────


class StageConfigDocument(Document):
    """MongoDB document that stores the configuration for one pipeline stage.

    The four built-in stages (ingestion, testcase, execution, reporting) are
    seeded on startup.  Admins may reorder or disable stages, or create
    entirely new custom stages (``is_builtin=False``).

    Stages execute in ascending ``order`` — the four seeded stages use orders
    100, 200, 300, and 400, leaving plenty of room for custom stages to be
    inserted between or after them.

    Attributes:
        stage_id:        Unique slug, e.g. ``"testcase"``.
        display_name:    Human-readable stage name shown in the UI.
        description:     Optional longer description of what this stage does.
        order:           Ascending execution order; lower values run first.
        enabled:         When ``False`` the entire stage is skipped.
        crew_type:       Execution strategy —
                         ``"pure_python"`` | ``"crewai_sequential"`` |
                         ``"crewai_hierarchical"``.
        timeout_seconds: Maximum wall-clock seconds allowed for this stage
                         (0 = no timeout).
        is_builtin:      ``True`` for the four seeded stages; ``False`` for
                         admin-created stages.  Builtin stages cannot be
                         deleted.
        input_schema:    Optional JSON-Schema dict describing expected stage
                         inputs (informational / validation use).
        output_schema:   Optional JSON-Schema dict describing expected stage
                         outputs.
        created_at:      UTC timestamp set once on insert.
        updated_at:      UTC timestamp refreshed on every update.
    """

    stage_id: Indexed(str, unique=True)  # type: ignore[valid-type]
    display_name: str
    description: str = ""
    order: int  # execution order; stages run ascending
    enabled: bool = True
    crew_type: str = (
        "crewai_sequential"  # pure_python | crewai_sequential | crewai_hierarchical
    )
    timeout_seconds: int = 300
    is_builtin: bool = True  # True for 4 default stages, False for user-created
    input_schema: Optional[dict] = None  # type: ignore[type-arg]
    output_schema: Optional[dict] = None  # type: ignore[type-arg]
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    class Settings:
        """Beanie collection settings."""

        name = "stage_configs"
        indexes = [
            [("order", 1)],
            [("enabled", 1), ("order", 1)],
        ]


# ─────────────────────────────────────────────────────────────────────────────
# PipelineRunDocument
# ─────────────────────────────────────────────────────────────────────────────


class PipelineRunDocument(Document):
    """MongoDB document tracking one end-to-end pipeline execution.

    A new :class:`PipelineRunDocument` is created each time a user uploads a
    requirements document and triggers a run.  It acts as the single source of
    truth for the run's lifecycle, storing the overall status, per-agent
    statuses, and lightweight summaries of each stage's output.

    Full per-agent output blobs are stored separately in
    :class:`PipelineResultDocument` and referenced by ``run_id``.

    Attributes:
        run_id:                 UUID string that uniquely identifies this run.
        document_name:          Original filename of the uploaded document.
        document_path:          Server-side path where the file was saved.
        llm_profile_id:         ObjectId string of the LLM profile override for
                                this run, or ``None`` to use the global default.
        status:                 Lifecycle state — ``pending`` | ``running`` |
                                ``paused`` | ``completed`` | ``failed`` |
                                ``cancelled``.
        current_stage:          ``stage_id`` of the stage currently executing,
                                or ``None`` when the run is not active.
        completed_stages:       Ordered list of ``stage_id`` values that have
                                finished successfully.
        agent_statuses:         Mapping of ``agent_id`` → status string
                                (waiting | running | done | skipped | error).
        stage_results_summary:  Shallow per-stage summary dicts (e.g. counts,
                                headline metrics) for quick display in the UI
                                without fetching full result documents.
        error:                  Human-readable error message if the run failed.
        pause_reason:           Why the run was paused (set by the pipeline
                                runner when transitioning to ``paused``).
        created_at:             UTC timestamp set when the record is inserted.
        started_at:             UTC timestamp set when execution begins.
        paused_at:              UTC timestamp set when the run enters ``paused``.
        resumed_at:             UTC timestamp set when the run is resumed.
        finished_at:            UTC timestamp set when the run reaches a
                                terminal state (completed / failed / cancelled).
    """

    run_id: Indexed(str, unique=True)  # type: ignore[valid-type]  # UUID string
    document_name: str
    document_path: str
    llm_profile_id: Optional[str] = None
    status: Indexed(str) = "pending"  # type: ignore[valid-type]
    current_stage: Optional[str] = None
    completed_stages: list[str] = Field(default_factory=list)
    agent_statuses: dict[str, str] = Field(default_factory=dict)
    stage_results_summary: dict[str, dict] = Field(default_factory=dict)  # type: ignore[type-arg]
    error: Optional[str] = None
    pause_reason: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)
    started_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None
    resumed_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    class Settings:
        """Beanie collection settings."""

        name = "pipeline_runs"
        indexes = [
            "status",
            [("created_at", -1)],
        ]


# ─────────────────────────────────────────────────────────────────────────────
# PipelineResultDocument
# ─────────────────────────────────────────────────────────────────────────────


class PipelineResultDocument(Document):
    """MongoDB document storing the full output of a single agent within a run.

    One :class:`PipelineResultDocument` is inserted for each agent that
    completes successfully.  The ``output`` field accepts any JSON-serialisable
    Python value — dicts, lists, and strings are all valid — and is stored as
    native BSON, so no ``json.dumps`` / ``json.loads`` round-trip is required.

    Documents are linked back to their parent run through ``run_id`` (a UUID
    string, not an ObjectId), and can be queried efficiently by the compound
    indexes on ``(run_id, stage)`` and ``(run_id, agent_id)``.

    Attributes:
        run_id:     UUID string matching :attr:`PipelineRunDocument.run_id`.
        stage:      Stage slug this output belongs to, e.g. ``"testcase"``.
        agent_id:   Agent slug that produced the output, e.g.
                    ``"requirement_analyzer"``.
        output:     Raw agent output — stored as native BSON (dict, list, or
                    scalar).  No serialisation needed on read.
        created_at: UTC timestamp set when the document is inserted.
    """

    run_id: Indexed(str)  # type: ignore[valid-type]
    stage: str
    agent_id: str
    output: Any  # stored as native BSON — no json.dumps needed
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        """Beanie collection settings."""

        name = "pipeline_results"
        indexes = [
            [("run_id", 1), ("stage", 1)],
            [("run_id", 1), ("agent_id", 1)],
        ]
