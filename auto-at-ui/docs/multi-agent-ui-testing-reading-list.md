# Reading list — multi-agent systems for UI test automation

This list supports the product direction in the milestone roadmap:
**deterministic Playwright execution**, with AI used only for auditable triage
and human-approved healing proposals. The runner remains the sole verdict
authority.

## Suggested reading order

Read the six core papers first. They provide enough grounding to design Phase 4
(governed intelligence) and Phase 5 (thesis benchmark) without prematurely
adding autonomous browser control.

1. **ReAct: Synergizing Reasoning and Acting in Language Models** (Yao et al.,
   ICLR 2023) — [paper](https://arxiv.org/abs/2210.03629)
   - Learn the `reason -> action/tool -> observation` loop.
   - Apply it to structured evidence analysis, not to an agent deciding test
     verdicts.

2. **AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation**
   (Wu et al., 2023) — [paper](https://arxiv.org/abs/2308.08155)
   - Learn interaction patterns, tool boundaries, and human-in-the-loop
     orchestration.
   - Use the concepts; adopting its framework is not a requirement.

3. **MetaGPT: Meta Programming for a Multi-Agent Collaborative Framework**
   (Hong et al., 2023) — [paper](https://arxiv.org/abs/2308.00352)
   - Learn role separation and standardized operating procedures (SOPs).
   - Maps well to `triage agent -> healing proposer -> reviewer`, with typed
     artefacts rather than unconstrained chat.

4. **A Survey on LLM-based Multi-Agent Systems: Workflow, Infrastructure, and
   Challenges** (Guo et al., 2024) —
   [paper](https://link.springer.com/article/10.1007/s44336-024-00009-2)
   - Use as the taxonomy for topology, communication, coordination, memory,
     and multi-agent failure modes.

5. **Semantic Test Repair for Web Applications (Semter)** (ESEC/FSE 2023) —
   [paper](https://2023.esec-fse.org/details/fse-2023-research-papers/83/-Remote-Semantic-Test-Repair-for-Web-applications)
   - Directly relevant to locator breakage and semantic repair proposals.
   - Compare its repair evidence and ranking ideas with `HealingProposal`.

6. **WebArena: A Realistic Web Environment for Building Autonomous Agents**
   (Zhou et al., 2023) — [paper](https://arxiv.org/abs/2307.13854)
   - Learn how to construct reproducible web tasks and measure outcomes.
   - Use it as benchmark-design inspiration, rather than as the target system.

## UI testing and self-healing

7. **DroidAgent: Autonomous Large Language Model Agents Enabling Intent-Driven
   Mobile GUI Testing** (Yoon, Feldt, Yoo, 2023) —
   [paper](https://arxiv.org/abs/2311.08649)
   - Relevant concepts: intent-level testing and short-/long-term memory.
   - Mobile-specific implementation; transfer only the concepts to web UI.

8. **An Automated Model-Based Approach to Repair Test Suites of Evolving Web
   Applications** (2020) —
   [paper](https://www.sciencedirect.com/science/article/pii/S0164121220302314)
   - A non-LLM repair baseline using DOM and screen information.
   - Important comparison point: use deterministic repair before escalating to
     an LLM proposal.

9. **A Locator Repair Method for GUI Test Scripts Using Distributed
   Representation** (2020) —
   [paper](https://www.jstage.jst.go.jp/article/jssst/37/4/37_4_24/_article/-char/en)
   - Covers similarity and ranking signals for locator candidates.
   - Useful when defining proposal confidence and evidence references.

10. **A Study on the Lifecycle of Flaky Tests** (Lam et al., ICSE 2020) —
    [paper](https://conf.researchr.org/details/icse-2020/icse-2020-papers/11/A-Study-on-the-Lifecycle-of-Flaky-Tests)
    - Grounds the flaky/environment category in triage.
    - Protects against false healing caused by misclassifying an intermittent
      failure as a locator defect.

11. **Large Language Models as Test Case Generators: Performance Evaluation and
    Enhancement** (Li and Yuan, 2024) —
    [paper](https://arxiv.org/abs/2404.13340)
    - TestChain separates testing subtasks instead of asking one LLM to do all
      reasoning.
    - Adapt this idea to separate failure classification from repair-candidate
      generation.

## Multi-agent planning, memory, and evaluation

12. **Understanding the Planning of LLM Agents: A Survey** (2024) —
    [paper](https://arxiv.org/abs/2402.02716)
    - Supports task decomposition, stop conditions, budget limits, reflection,
      and memory design.

13. **Reflexion: Language Agents with Verbal Reinforcement Learning**
    (Shinn et al., NeurIPS 2023) —
    [paper](https://arxiv.org/abs/2303.11366)
    - Treat deterministic rerun results as feedback for future proposals.
    - Do not promote episodic memory until independently validated, as required
      by Phase 4.

14. **WorkArena: How Capable Are Web Agents at Solving Common Knowledge Work
    Tasks?** (2024) — [paper](https://arxiv.org/abs/2403.07718)
    - Additional reference for realistic web task definitions and completion
      criteria.

15. **OSWorld: Benchmarking Multimodal Agents for Open-Ended Tasks in Real
    Computer Environments** (2024) — [paper](https://arxiv.org/abs/2404.07972)
    - Read when adding screenshot/visual evidence beyond DOM-based Playwright.
    - Not required for the first deterministic web vertical slice.

16. **FLARE: Agentic Coverage-Guided Fuzzing for LLM-Based Multi-Agent
    Systems** (2026) — [paper](https://arxiv.org/abs/2604.05289)
    - Relevant to testing loops, failed tool calls, and handoffs between agents.
    - Inspires multi-agent coverage measures in addition to UI scenario
      coverage.

## Governance and safety

17. **Agent-SafetyBench: Evaluating the Safety of LLM Agents** (2025) —
    [paper](https://arxiv.org/abs/2412.14470)
    - Supports tests for unsafe tool use, data handling, and authority
      violations.

18. **Agent Security Bench: Formalizing and Benchmarking Attacks and Defenses
    in LLM-Based Agents** (ICLR 2025) —
    [paper](https://mlanthology.org/iclr/2025/zhang2025iclr-agent/)
    - Read before exposing evidence, browser data, or memory to agents.
    - Consider prompt injection through logs, DOM text, screenshots, and stored
      memory as untrusted input.

19. **Towards Verifiably Safe Tool Use for LLM Agents** (2026) —
    [paper](https://arxiv.org/abs/2601.08012)
    - Supports enforceable policy/tool boundaries rather than relying on prompts
      alone.
    - Aligns with the rule that agents create proposals but cannot change a
      verdict, source, database, shell, or browser profile.

## Thesis implementation hypothesis

Compare these conditions on the same versioned, seeded benchmark manifest:

1. Deterministic Playwright baseline.
2. Single-agent triage.
3. Multi-agent triage plus ranked healing proposal.
4. Selected-evidence ablation.

Report precision, recall, F1, valid-healing rate, false-healing rate, median
triage/recovery time, token cost, overhead, and repeatability. A proposed repair
is only valid after named human approval and an independent deterministic rerun.
