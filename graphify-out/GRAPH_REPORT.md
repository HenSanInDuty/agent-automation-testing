# Graph Report - backend/app + docs  (2026-05-01)

## Corpus Check
- 78 files · ~71,013 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1180 nodes · 3712 edges · 37 communities detected
- Extraction: 34% EXTRACTED · 66% INFERRED · 0% AMBIGUOUS · INFERRED: 2462 edges (avg confidence: 0.51)
- Token cost: 0 input · 0 output

## God Nodes (most connected - your core abstractions)
1. `PipelineNodeConfig` - 102 edges
2. `StageConfigDocument` - 89 edges
3. `LLMProfileDocument` - 86 edges
4. `AgentConfigDocument` - 84 edges
5. `PipelineTemplateDocument` - 84 edges
6. `PipelineEdgeConfig` - 83 edges
7. `PipelineStatus` - 83 edges
8. `AgentConfigSummary` - 79 edges
9. `PipelineRunDocument` - 74 edges
10. `PipelineAgentGroup` - 74 edges

## Surprising Connections (you probably didn't know these)
- `ChatRequest` --shares_data_with--> `LLMProfileDocument`  [INFERRED]
  backend\app\api\v1\chat.py → docs/data-models.md
- `Settings` --rationale_for--> `Apache Kafka 3.9.0 KRaft`  [INFERRED]
  backend\app\config.py → docs/architecture.md
- `Settings` --rationale_for--> `MongoDB (Beanie ODM)`  [INFERRED]
  backend\app\config.py → docs/architecture.md
- `lifespan()` --calls--> `WebSocketManager`  [EXTRACTED]
  backend\app\main.py → docs/architecture.md
- `create_app()` --calls--> `CORSMiddleware`  [EXTRACTED]
  backend\app\main.py → docs/architecture.md

## Hyperedges (group relationships)
- **DAG Pipeline Execution Core** — architecture_dagpipelinerunner, architecture_dagresolver, architecture_signalmanager [EXTRACTED 0.95]
- **LLM Resolution Chain (AgentFactory → LLMFactory → LLMProfile)** — architecture_agentfactory, architecture_llmfactory, datamodels_llmprofiledocument [EXTRACTED 0.95]
- **Observability Pipeline (EventBus → Kafka → ClickHouse)** — architecture_eventbus, architecture_kafka, architecture_clickhouse [EXTRACTED 0.95]
- **V3 DAG Pipeline Execution Flow** — pipeline_background, core_dag_pipeline_runner, core_dag_resolver [EXTRACTED 0.95]
- **WebSocket Real-Time Event Broadcasting Pipeline** — pipeline_background, websocket_manager, websocket_pipeline_ws [EXTRACTED 0.95]
- **Agent LLM Override Resolution Chain** — core_agent_factory, core_llm_factory, agent_configs_helpers [INFERRED 0.80]
- **Four-Stage Pipeline Crew Chain** — ingestion_crew_IngestionCrew, testcase_crew_TestcaseCrew, execution_crew_ExecutionCrew, reporting_crew_ReportingCrew [EXTRACTED 0.95]
- **Beanie MongoDB Document Registry** — models_LLMProfileDocument, models_AgentConfigDocument, models_StageConfigDocument, models_PipelineRunDocument, models_PipelineResultDocument, models_PipelineTemplateDocument [EXTRACTED 1.00]
- **CrewAI-Based Crew Implementations** — testcase_crew_TestcaseCrew, execution_crew_ExecutionCrew, reporting_crew_ReportingCrew, dynamic_crew_DynamicCrewAICrew [INFERRED 0.90]
- **Four-Stage Pipeline IO Data Contract** — pipeline_io_IngestionOutput, pipeline_io_TestCaseOutput, pipeline_io_ExecutionOutput, pipeline_io_PipelineReport [EXTRACTED 0.95]
- **Report Generation Flow** — export_service_ExportService, docx_builder_DocxReportBuilder, pipeline_io_PipelineReport [EXTRACTED 0.95]
- **API Test Execution Tools Triad** — api_runner_run_api_request, config_loader_load_env_config, execution_tasks_make_test_runner_task [INFERRED 0.80]

## Communities

### Community 0 - "Core Architecture & Factories"
Cohesion: 0.04
Nodes (104): ABC, AgentFactory, Async factory that builds CrewAI ``Agent`` objects from MongoDB config.      T, APIRunnerTool, CrewAI tool that executes HTTP API requests.          Designed for use by the, Execute the API request and return JSON-formatted result., Stub – crewai is not installed.  Install crewai to use this tool., crews/artifact_crew.py ────────────────────── Artifact Generation crew — pure (+96 more)

### Community 1 - "Agent Config & Schema Layer"
Cohesion: 0.13
Nodes (130): AgentConfigByPipelineResponse, AgentConfigCreate, AgentConfigGrouped, AgentConfigGroupedResponse, AgentConfigResetResponse, AgentConfigResponse, AgentConfigSummary, AgentConfigUpdate (+122 more)

### Community 2 - "Pipeline Execution & Crews"
Cohesion: 0.06
Nodes (91): ArtifactCrew, pipeline/_background.py – Background task functions for pipeline execution., Background task for the V3 DAG pipeline runner., Async background task that drives the V2 full pipeline for one run., _run_dag_pipeline_background(), _run_pipeline_background(), BaseCrew, Create a new pipeline template. (+83 more)

### Community 3 - "Pipeline Control & Templates"
Cohesion: 0.03
Nodes (94): cancel_pipeline(), pause_pipeline(), pipeline/control.py – Pause / resume / cancel endpoints for pipeline runs.  En, Request cancellation of a running, paused, or pending pipeline., Request that a running pipeline pause after the current stage., Request that a paused pipeline resume execution., resume_pipeline(), _dag_run_to_response() (+86 more)

### Community 4 - "Agent Factory & LLM Layer"
Cohesion: 0.04
Nodes (60): build_agent(), core/agent_factory.py – Build CrewAI Agent instances from DB configuration.  O, Build multiple agents at once.          Args:             agent_ids:    List, Build all enabled agents belonging to a specific pipeline stage.          Fetc, Return the :class:`~app.db.models.AgentConfigDocument` for *agent_id*., Walk the LLM override chain and return the first resolved LLM object., Async module-level convenience wrapper around :class:`AgentFactory`.      Args, Build a CrewAI ``Agent`` for the given *agent_id*.          The LLM override c (+52 more)

### Community 5 - "LLM & Chat API"
Cohesion: 0.06
Nodes (67): BaseModel, _build_litellm_kwargs(), chat_send(), ChatMessage, ChatRequest, list_chat_profiles(), _normalize_ollama_base_url(), ProfileSummary (+59 more)

### Community 6 - "API Runner & Task Agents"
Cohesion: 0.04
Nodes (72): API Runner CrewAI Tool, _APIRunnerInput, _empty_result(), tools/api_runner.py ─────────────────── HTTP API execution tool for the Execut, Execute a list of API requests sequentially and return all results.      Each, Execute a single HTTP request and return a structured result dictionary., run_api_request(), run_api_requests_batch() (+64 more)

### Community 7 - "Pipeline Template CRUD"
Cohesion: 0.05
Nodes (63): append_pipeline_node(), archive_template(), bulk_init_agent_statuses(), clone_pipeline_template(), count_agents_by_stage(), count_runs_for_template(), create_agent_config(), create_dag_run() (+55 more)

### Community 8 - "System Architecture Docs"
Cohesion: 0.05
Nodes (43): ClickHouse 24.8, CORSMiddleware, DAGPipelineRunner, DAGResolver, EventBus, ExportService, Apache Kafka 3.9.0 KRaft, MongoDB (Beanie ODM) (+35 more)

### Community 9 - "Artifact Generation Stage"
Cohesion: 0.06
Nodes (45): AgentConfigCreate Schema, AgentConfigGrouped Schema, AgentConfigResponse Schema, ArtifactCrew, BaseCrew Abstract Base, ProgressCallback Type Alias, Async CRUD Layer, init_db (+37 more)

### Community 10 - "DAG Pipeline Runner V3"
Cohesion: 0.07
Nodes (27): DAGPipelineRunner (V3), DAGResolver, PipelineRunnerV2 (V2 Deprecated), Pipeline Background Task Functions, Pipeline Control Endpoints (Pause/Resume/Cancel), Pipeline API Shared Helpers, Pipeline Results and Export Endpoints, Combined Pipeline APIRouter (+19 more)

### Community 11 - "Document Parser Tools"
Cohesion: 0.07
Nodes (31): _parse_csv(), parse_document(), parse_docx(), parse_excel(), parse_pdf(), tools/document_parser.py ──────────────────────── Document parsing utilities f, Extract text from a DOCX (Word) file using *python-docx*.      Extracts both b, Extract text from an Excel workbook (.xlsx / .xls) using *openpyxl*.      Each (+23 more)

### Community 12 - "Dynamic CrewAI Orchestration"
Cohesion: 0.11
Nodes (19): DynamicCrewAICrew, crews/dynamic_crew.py – Generic CrewAI crew for custom/dynamic pipeline stages., Return mock output for development/testing., Generic CrewAI crew that builds agents dynamically from AgentConfigDocuments., Execute the crew synchronously (called via asyncio.to_thread in runner)., _now(), PipelineRunnerV2, Execute the full pipeline end-to-end.          Loads all enabled stages from M (+11 more)

### Community 13 - "LLM Abstraction & Providers"
Cohesion: 0.09
Nodes (26): CrewAI Agent, CrewAI Crew, LiteLLM Abstraction, LLM Resolution 5-Tier Priority, AgentFactory, APIRunnerTool, ConfigLoaderTool, DocumentParser Tool (+18 more)

### Community 14 - "Stage Config Management"
Cohesion: 0.19
Nodes (20): schemas/stage_config.py – Pydantic schemas for pipeline stage configurations., Stage config as returned by the API., Reorder stages by providing ordered list of stage_ids., StageConfigResponse, StageReorderRequest, create_stage_config(), delete_stage_config(), get_stage_config() (+12 more)

### Community 15 - "Event Bus & Observability"
Cohesion: 0.12
Nodes (13): _base_fields(), EventBus, _now_iso(), services/event_bus.py – Fire-and-forget Kafka event producer.  All ``emit*`` c, Flush and close the producer. Called from the FastAPI lifespan., Publish *payload* to ``<KAFKA_TOPIC_PREFIX>.<topic_suffix>``.          Always, Schedule an async ``emit()`` from synchronous context.          Uses ``asyncio, Emit a run-level lifecycle event to the ``pipeline_events`` topic.          De (+5 more)

### Community 16 - "Signal Manager Pause/Cancel"
Cohesion: 0.1
Nodes (11): core/signal_manager.py – In-memory signal store for pipeline pause/resume/cancel, Return True if a CANCEL signal is currently pending., Return True if a PAUSE signal is currently pending., Return the number of run IDs with a pending signal., In-memory signal store for pipeline runs.      Signals are set from API handle, Set a signal for a pipeline run., Get the current signal for a run., Clear the signal and resume event for a run (cleanup after terminal state). (+3 more)

### Community 17 - "Test File Renderer"
Cohesion: 0.15
Nodes (19): _file_stem(), group_test_cases(), _pascal(), tools/test_file_renderer.py ─────────────────────────── Generates runnable uni, Render a test file for the given language.      Returns:         ``(filename,, Generate a human-readable Markdown test case specification document., Extract and organise test data fixtures from the test cases., Convert arbitrary text to snake_case identifier. (+11 more)

### Community 18 - "Config Loader Tool"
Cohesion: 0.14
Nodes (17): Config Loader CrewAI Tool, build_auth_headers(), _coerce_env_value(), ConfigLoaderInput, list_available_environments(), load_env_config(), merge_headers(), _post_process() (+9 more)

### Community 19 - "Beanie ODM Collection Config"
Cohesion: 0.5
Nodes (4): Beanie collection settings., Beanie collection settings., Beanie collection settings., Settings

### Community 20 - "Agent Config Route Helpers"
Cohesion: 0.5
Nodes (4): Agent Config Shared Helpers, Agent Config Route Handlers, AgentFactory, LLMFactory / build_llm

### Community 21 - "DAG Validation Schemas"
Cohesion: 1.0
Nodes (2): DAG Validation Response Schema, Pipeline Template Create Schema

### Community 22 - "Config String Utilities"
Cohesion: 1.0
Nodes (1): Strip leading/trailing whitespace from the raw origins string.

### Community 23 - "Config CSV Parser"
Cohesion: 1.0
Nodes (1): Split the comma-separated ``ALLOWED_ORIGINS`` string into a list.

### Community 24 - "App Debug Mode"
Cohesion: 1.0
Nodes (1): Return ``True`` when ``APP_ENV`` is ``"development"``.

### Community 25 - "App Environment Helpers"
Cohesion: 1.0
Nodes (1): Return ``True`` when ``APP_ENV`` is ``"production"``.

### Community 26 - "File Size Conversion"
Cohesion: 1.0
Nodes (1): Convert :attr:`MAX_FILE_SIZE_MB` to bytes.

### Community 27 - "Crew Run Interface"
Cohesion: 1.0
Nodes (1): Execute this crew and return structured output.          Args:             in

### Community 28 - "JSON Parsing Utilities"
Cohesion: 1.0
Nodes (1): Best-effort JSON parser for CrewAI task outputs.          CrewAI returns diffe

### Community 29 - "API Key Required Providers"
Cohesion: 1.0
Nodes (1): Providers that require an API key.

### Community 30 - "Free Tier Providers"
Cohesion: 1.0
Nodes (1): Providers that typically require a base URL.

### Community 31 - "LiteLLM Model Prefix"
Cohesion: 1.0
Nodes (1): LiteLLM model string prefix for this provider.

### Community 32 - "API Key Masking"
Cohesion: 1.0
Nodes (1): Mask the raw api_key before Pydantic stores it.          Works both when *data

### Community 33 - "LiteLLM Style Helper"
Cohesion: 1.0
Nodes (1): Return the LiteLLM-style ``'provider/model'`` string.

### Community 34 - "Frontend Architecture"
Cohesion: 1.0
Nodes (1): Next.js Frontend (React Flow UI)

### Community 35 - "DB Lifecycle"
Cohesion: 1.0
Nodes (1): close_db

### Community 36 - "Stage Reorder Schema"
Cohesion: 1.0
Nodes (1): Stage Reorder Request Schema

## Knowledge Gaps
- **259 isolated node(s):** `Application settings loaded from environment variables and/or a ``.env`` file.`, `Strip leading/trailing whitespace from the raw origins string.`, `Split the comma-separated ``ALLOWED_ORIGINS`` string into a list.`, `Return ``True`` when ``APP_ENV`` is ``"development"``.`, `Return ``True`` when ``APP_ENV`` is ``"production"``.` (+254 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `DAG Validation Schemas`** (2 nodes): `DAG Validation Response Schema`, `Pipeline Template Create Schema`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Config String Utilities`** (1 nodes): `Strip leading/trailing whitespace from the raw origins string.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Config CSV Parser`** (1 nodes): `Split the comma-separated ``ALLOWED_ORIGINS`` string into a list.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `App Debug Mode`** (1 nodes): `Return ``True`` when ``APP_ENV`` is ``"development"``.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `App Environment Helpers`** (1 nodes): `Return ``True`` when ``APP_ENV`` is ``"production"``.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `File Size Conversion`** (1 nodes): `Convert :attr:`MAX_FILE_SIZE_MB` to bytes.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Crew Run Interface`** (1 nodes): `Execute this crew and return structured output.          Args:             in`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `JSON Parsing Utilities`** (1 nodes): `Best-effort JSON parser for CrewAI task outputs.          CrewAI returns diffe`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `API Key Required Providers`** (1 nodes): `Providers that require an API key.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Free Tier Providers`** (1 nodes): `Providers that typically require a base URL.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `LiteLLM Model Prefix`** (1 nodes): `LiteLLM model string prefix for this provider.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `API Key Masking`** (1 nodes): `Mask the raw api_key before Pydantic stores it.          Works both when *data`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `LiteLLM Style Helper`** (1 nodes): `Return the LiteLLM-style ``'provider/model'`` string.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Frontend Architecture`** (1 nodes): `Next.js Frontend (React Flow UI)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `DB Lifecycle`** (1 nodes): `close_db`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Stage Reorder Schema`** (1 nodes): `Stage Reorder Request Schema`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `run_api_request()` connect `API Runner & Task Agents` to `Core Architecture & Factories`, `Config Loader Tool`?**
  _High betweenness centrality (0.119) - this node is a cross-community bridge._
- **Are the 99 inferred relationships involving `PipelineNodeConfig` (e.g. with `CloneTemplateRequest` and `PaginatedTemplateResponse`) actually correct?**
  _`PipelineNodeConfig` has 99 INFERRED edges - model-reasoned connections that need verification._
- **Are the 86 inferred relationships involving `StageConfigDocument` (e.g. with `db/crud.py – Async CRUD operations using Beanie ODM.  All functions are async` and `Return the current UTC datetime (timezone-aware).`) actually correct?**
  _`StageConfigDocument` has 86 INFERRED edges - model-reasoned connections that need verification._
- **Are the 83 inferred relationships involving `LLMProfileDocument` (e.g. with `api/v1/llm_profiles.py – REST endpoints for LLM profile administration.  All r` and `Fetch an LLM profile by ObjectId string, or raise HTTP 404.      Args:`) actually correct?**
  _`LLMProfileDocument` has 83 INFERRED edges - model-reasoned connections that need verification._
- **Are the 81 inferred relationships involving `AgentConfigDocument` (e.g. with `pipeline_templates/_helpers.py – Shared helpers, models, and validators for pip` and `Fetch an agent config by slug, or raise HTTP 404.`) actually correct?**
  _`AgentConfigDocument` has 81 INFERRED edges - model-reasoned connections that need verification._
- **Are the 81 inferred relationships involving `PipelineTemplateDocument` (e.g. with `DAGPipelineRunner` and `core/dag_pipeline_runner.py – V3 DAG-based pipeline execution engine.  Execute`) actually correct?**
  _`PipelineTemplateDocument` has 81 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Application settings loaded from environment variables and/or a ``.env`` file.`, `Strip leading/trailing whitespace from the raw origins string.`, `Split the comma-separated ``ALLOWED_ORIGINS`` string into a list.` to the rest of the system?**
  _259 weakly-connected nodes found - possible documentation gaps or missing edges._