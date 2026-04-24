# Luồng Agent Factory & LLM Resolution

## 1. Luồng phân giải LLM Profile (5 tầng ưu tiên)

```mermaid
flowchart TD
    START["DAGRunner gọi\nAgentFactory.build(agent_id, override_profile_id?)"]

    P1{"Node config có\nllm_profile_id?"}
    P2{"AgentConfig DB\ncó llm_profile_id?"}
    P3{"Run-level\nllm_profile_id?"}
    P4{"DB có profile\nwith is_default=true?"}
    P5["ENV fallback\nDEFAULT_LLM_PROVIDER\nDEFAULT_LLM_MODEL\nDEFAULT_LLM_API_KEY"]

    USE1["Dùng node-level override"]
    USE2["Dùng agent's profile"]
    USE3["Dùng run-level profile"]
    USE4["Dùng default profile"]
    USE5["Dùng ENV profile\n(no DB lookup)"]

    LLM_FACTORY["LLMFactory.build(profile)\n→ LiteLLM ChatLLM object"]
    CREWAI_AGENT["crewai.Agent(\n  role=..., goal=...,\n  backstory=...,\n  llm=llm_object,\n  verbose=...,\n  max_iter=...\n)"]

    START --> P1
    P1 -- Có --> USE1 --> LLM_FACTORY
    P1 -- Không --> P2
    P2 -- Có --> USE2 --> LLM_FACTORY
    P2 -- Không --> P3
    P3 -- Có --> USE3 --> LLM_FACTORY
    P3 -- Không --> P4
    P4 -- Có --> USE4 --> LLM_FACTORY
    P4 -- Không --> P5 --> LLM_FACTORY
    LLM_FACTORY --> CREWAI_AGENT

    style USE1 fill:#dbeafe,stroke:#3b82f6
    style USE2 fill:#e0f2fe,stroke:#0ea5e9
    style USE3 fill:#f0fdf4,stroke:#16a34a
    style USE4 fill:#fef3c7,stroke:#f59e0b
    style USE5 fill:#fce7f3,stroke:#ec4899
```

---

## 2. LLM Factory — provider matrix

```mermaid
flowchart LR
    subgraph Profile["LLMProfileDocument"]
        PROV["provider"]
        MODEL["model"]
        APIKEY["api_key"]
        BASEURL["base_url (optional)"]
        TEMP["temperature"]
        MAXTOK["max_tokens"]
    end

    subgraph LiteLLM["LiteLLM format"]
        FMT["{provider}/{model}\ne.g. openai/gpt-4o"]
    end

    subgraph Providers["Supported Providers"]
        OAI["openai\nopenai/gpt-4o\nopenai/gpt-4o-mini"]
        ANT["anthropic\nanthropic/claude-3-5-sonnet-20241022"]
        OLL["ollama\nollama/llama3\n(no API key, base_url required)"]
        AZ["azure_openai\nazure/gpt-4o\n(requires base_url, api_version)"]
        GROQ["groq\ngroq/llama-3.1-70b-versatile"]
        HF["huggingface\nhuggingface/ibm-granite/..."]
        LMS["lm_studio\n(OpenAI-compatible local,\nno API key)"]
    end

    Profile --> LiteLLM
    LiteLLM --> OAI
    LiteLLM --> ANT
    LiteLLM --> OLL
    LiteLLM --> AZ
    LiteLLM --> GROQ
    LiteLLM --> HF
    LiteLLM --> LMS
```

---

## 3. Agent Catalog → Node → Crew execution

```mermaid
flowchart TD
    subgraph DB["MongoDB"]
        AC[("agent_configs\n{agent_id, role, goal,\nbackstory, llm_profile_id,\nenabled, max_iter}")]
        LP[("llm_profiles\n{profile_id, provider,\nmodel, api_key,...}")]
    end

    subgraph Template["PipelineTemplate (node)"]
        NODE["PipelineNodeConfig\n{node_id, node_type='agent',\nagent_id, timeout_seconds,\nretry_count,\nconfig_overrides{}}"]
    end

    subgraph Factory["AgentFactory.build()"]
        LOAD_AC["get_agent_config(agent_id)"]
        RESOLVE_LLM["resolve_llm_profile()\n5-tier priority"]
        BUILD_LLM["LLMFactory.build(profile)\n→ ChatLLM"]
        BUILD_AGENT["crewai.Agent(\n  role, goal, backstory,\n  llm, verbose, max_iter\n)"]
    end

    subgraph Crew["CrewAI Execution"]
        TASK["crewai.Task(\n  description=context_text,\n  agent=agent,\n  expected_output=...\n)"]
        CREW["crewai.Crew(\n  agents=[agent],\n  tasks=[task],\n  process=sequential\n)"]
        KICKOFF["asyncio.to_thread(\n  crew.kickoff\n)"]
    end

    NODE -->|"agent_id lookup"| LOAD_AC
    AC --> LOAD_AC
    LP --> RESOLVE_LLM
    LOAD_AC --> RESOLVE_LLM --> BUILD_LLM --> BUILD_AGENT
    BUILD_AGENT --> TASK --> CREW --> KICKOFF

    KICKOFF -->|"CrewOutput"| RESULT["output_data\nsaved to pipeline_results"]

    style RESULT fill:#dcfce7,stroke:#22c55e
```

---

## 4. 4 Built-in Crews — cấu trúc agents

```mermaid
graph TB
    subgraph Ingestion["IngestionCrew (Layer 1)"]
        I1["document_parser\nExtract text từ PDF/DOCX/TXT\nDùng: DocumentParser tool"]
        I2["ingestion_splitter\nChia thành chunks\nDùng: TextChunker tool"]
        I3["requirement_normalizer\nChuẩn hóa → RequirementItem[]"]
        I1 --> I2 --> I3
    end

    subgraph Testcase["TestcaseCrew (Layer 2)"]
        direction LR
        T1["requirement_analyzer"] --> T2["scope_classifier"]
        T2 --> T3["data_model_agent"]
        T3 --> T4["rule_parser"]
        T4 --> T5["test_condition_agent"]
        T5 --> T6["dependency_agent"]
        T6 --> T7["test_case_generator"]
        T7 --> T8["automation_agent"]
        T8 --> T9["coverage_agent_pre"]
        T9 --> T10["report_agent_pre"]
    end

    subgraph Execution["ExecutionCrew (Layer 3)"]
        E1["execution_orchestrator"] --> E2["env_adapter\nDùng: ConfigLoaderTool"]
        E2 --> E3["test_runner\nDùng: APIRunnerTool"]
        E3 --> E4["execution_logger"]
        E4 --> E5["result_store"]
    end

    subgraph Reporting["ReportingCrew (Layer 4)"]
        R1["aggregator"] --> R2["risk_analyzer"]
        R2 --> R3["root_cause_analyzer"]
        R3 --> R4["executive_summarizer"]
        R4 --> R5["report_generator"]
    end

    Ingestion -->|"RequirementItem[]"| Testcase
    Testcase -->|"TestCase[]"| Execution
    Execution -->|"TestExecutionResult[]"| Reporting
```

---

## 5. Mock Mode — fallback khi không có LLM

```mermaid
flowchart LR
    ENV{"MOCK_CREWS=true\nor mock_mode=True?"}
    REAL["Thực thi thật\ncrewai.Crew.kickoff()\n→ gọi LLM API"]
    MOCK["Mock execution\nTraả về dữ liệu giả\ncó cấu trúc hợp lệ\nKHÔNG gọi LLM"]

    ENV -- Không --> REAL
    ENV -- Có --> MOCK

    MOCK --> MOCK_OUTPUT["Ingestion: 3 fake RequirementItem\nTestcase: 5 fake TestCase\nExecution: all pass\nReporting: summary report"]

    note1["Dùng cho:\n• CI/CD pipelines\n• Windows dev (no crewai)\n• Offline development\n• Integration testing"]

    MOCK_OUTPUT --> note1

    style MOCK fill:#f3f4f6,stroke:#9ca3af
    style MOCK_OUTPUT fill:#f3f4f6,stroke:#9ca3af
```
