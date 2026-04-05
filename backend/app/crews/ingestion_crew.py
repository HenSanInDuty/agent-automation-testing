from __future__ import annotations

"""
crews/ingestion_crew.py
───────────────────────
Ingestion pipeline — pure Python, no CrewAI agents required.

Pipeline stages:
    1. parse_document()   – extract text from PDF / DOCX / Excel / TXT
    2. chunk_text()       – split into LLM-manageable overlapping chunks
    3. analyze_chunk()    – call LLM directly via litellm to extract requirements
    4. deduplicate()      – remove near-duplicate requirement titles
    5. assign_ids()       – assign sequential REQ-001 … REQ-NNN identifiers

The ingestion stage intentionally avoids CrewAI because:
  - It is primarily a data-extraction pipeline, not a reasoning loop.
  - It needs to process documents chunk-by-chunk in a tight loop.
  - litellm.completion() gives us full control over the request / response
    without CrewAI's overhead or lancedb dependency.

Usage::

    from app.crews.ingestion_crew import IngestionCrew

    crew = IngestionCrew(db=session, run_id="abc-123")
    result = crew.run({"file_path": "/uploads/spec.pdf"})
    # result is an IngestionOutput.model_dump() dict
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.llm_factory import LLMFactory, get_model_string
from app.crews.base_crew import BaseCrew, ProgressCallback
from app.schemas.pipeline_io import IngestionOutput, RequirementItem, RequirementType
from app.tools.document_parser import parse_document
from app.tools.text_chunker import chunk_text

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# LLM prompt template
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a requirements analyst. Your only job is to extract software requirements
from document chunks and return them as valid JSON.

Rules:
- Return ONLY a JSON object — no prose, no markdown fences, no explanations.
- If no requirements are found, return: {"requirements": []}
- Each requirement must be a clearly stated system or business need.
- Do NOT invent requirements — only extract what is explicitly stated or clearly implied.
"""

_USER_PROMPT_TEMPLATE = """\
Analyze the following document chunk and extract all software requirements mentioned.

For each requirement found, produce a JSON object with:
  title       – concise noun phrase (≤ 15 words)
  description – complete, self-contained description
  type        – functional | non_functional | constraint | assumption
  priority    – high | medium | low  (infer from keywords like "critical", "must", "should")
  tags        – list of domain tags / keywords (strings)
  notes       – any ambiguities or missing information (empty string if none)

Return a JSON object like:
{
  "requirements": [
    {
      "title": "...",
      "description": "...",
      "type": "functional",
      "priority": "medium",
      "tags": ["tag1"],
      "notes": ""
    }
  ]
}

Document chunk:
---
{chunk}
---
"""

# Minimum chunk length worth sending to the LLM (very short chunks are noise)
_MIN_CHUNK_FOR_LLM = 80


# ─────────────────────────────────────────────────────────────────────────────
# IngestionCrew
# ─────────────────────────────────────────────────────────────────────────────


class IngestionCrew(BaseCrew):
    """
    Pure-Python ingestion pipeline that parses a document and returns a
    structured list of software requirements via direct LLM calls.

    This class does NOT use CrewAI agents — it orchestrates the pipeline
    imperatively so that:
    - Each chunk can be processed independently (and in a retry loop).
    - LLM calls fail gracefully with a mock fallback when no profile is set.
    - Progress events are emitted after each chunk so the frontend can show
      a live progress bar.

    Attributes:
        stage:     Always "ingestion".
        agent_ids: Empty list (no CrewAI agents in this stage).
    """

    stage = "ingestion"
    agent_ids: list[str] = []  # no CrewAI agents

    def __init__(
        self,
        db: Session,
        run_id: str,
        run_profile_id: Optional[int] = None,
        progress_callback: Optional[ProgressCallback] = None,
        mock_mode: Optional[bool] = None,
        # Chunking parameters (can be overridden via input_data)
        chunk_size: int = 2000,
        chunk_overlap: int = 200,
        min_chunk_size: int = _MIN_CHUNK_FOR_LLM,
    ) -> None:
        super().__init__(
            db=db,
            run_id=run_id,
            run_profile_id=run_profile_id,
            progress_callback=progress_callback,
            mock_mode=mock_mode,
        )
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._min_chunk_size = min_chunk_size
        self._llm_factory = LLMFactory(db)

        # Lazy cache for the per-agent LLM profile lookup
        self._per_agent_profile_checked: bool = False
        self._per_agent_profile: Any = None  # LLMProfile | None

    # ─────────────────────────────────────────────────────────────────────────
    # Public entry point
    # ─────────────────────────────────────────────────────────────────────────

    def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the ingestion pipeline.

        Args:
            input_data: Dictionary with at minimum:
                ``file_path`` (str | Path) – path to the document to process.
                ``document_name`` (str)    – optional display name (defaults to filename).
                ``chunk_size`` (int)       – optional chunk size override (chars).
                ``chunk_overlap`` (int)    – optional overlap override (chars).
                ``mock_mode`` (bool)       – if True, skip LLM and use heuristic extraction.

        Returns:
            ``IngestionOutput.model_dump()`` — a plain dict that can be stored
            in the database or forwarded to the Test Case crew.

        Raises:
            FileNotFoundError: If the document file does not exist.
            ValueError: If the file format is not supported.
        """
        file_path = Path(input_data["file_path"])
        document_name = input_data.get("document_name") or file_path.name
        mock_mode: bool = bool(input_data.get("mock_mode", False))

        # Allow per-call chunk config overrides
        chunk_size = int(input_data.get("chunk_size", self._chunk_size))
        chunk_overlap = int(input_data.get("chunk_overlap", self._chunk_overlap))

        self._emit(
            "log",
            {"message": f"Starting ingestion for '{document_name}'", "level": "info"},
        )

        # ── Step 1: Parse ────────────────────────────────────────────────────
        self._emit(
            "log", {"message": f"Parsing document: {document_name}", "level": "info"}
        )
        try:
            raw_text = parse_document(file_path)
        except Exception as exc:
            error_msg = f"Document parsing failed: {exc}"
            logger.error("[Ingestion][%s] %s", self._run_id, error_msg)
            self._emit("log", {"message": error_msg, "level": "error"})
            raise

        logger.info(
            "[Ingestion][%s] Parsed '%s': %d chars",
            self._run_id,
            document_name,
            len(raw_text),
        )
        self._emit(
            "log",
            {"message": f"Parsed {len(raw_text):,} characters", "level": "info"},
        )

        # ── Step 2: Chunk ────────────────────────────────────────────────────
        chunks = chunk_text(raw_text, chunk_size=chunk_size, overlap=chunk_overlap)
        # Filter out chunks that are too short to contain useful information
        chunks = [c for c in chunks if len(c.strip()) >= self._min_chunk_size]

        self._emit_agent_started("ingestion_pipeline", "Document Ingestion")

        if not chunks:
            logger.warning(
                "[Ingestion][%s] Document '%s' produced no processable chunks.",
                self._run_id,
                document_name,
            )
            self._emit_agent_completed(
                "ingestion_pipeline",
                output_preview="Document appears empty — no processable chunks",
            )
            return IngestionOutput(
                requirements=[],
                document_name=document_name,
                total_requirements=0,
                chunks_processed=0,
                processing_notes=["Document appears to be empty or unreadable."],
            ).model_dump()

        logger.info(
            "[Ingestion][%s] Created %d chunks (size=%d, overlap=%d)",
            self._run_id,
            len(chunks),
            chunk_size,
            chunk_overlap,
        )
        self._emit(
            "log",
            {
                "message": f"Split into {len(chunks)} chunk(s) for analysis",
                "level": "info",
            },
        )

        # ── Step 3: Analyse each chunk ───────────────────────────────────────
        all_requirements: list[RequirementItem] = []
        processing_notes: list[str] = []

        for chunk_idx, chunk in enumerate(chunks, start=1):
            self._emit(
                "log",
                {
                    "message": f"Analyzing chunk {chunk_idx}/{len(chunks)} ({len(chunk):,} chars)",
                    "level": "info",
                },
            )
            self._emit(
                "agent.progress",
                {
                    "agent_id": "ingestion_pipeline",
                    "message": f"Chunk {chunk_idx}/{len(chunks)}",
                    "progress": round(chunk_idx / len(chunks) * 100),
                },
            )

            try:
                if mock_mode:
                    chunk_reqs = self._mock_extract(chunk, chunk_idx)
                    if chunk_idx == 1:
                        processing_notes.append(
                            "Mock mode: heuristic extraction used (no LLM)"
                        )
                else:
                    chunk_reqs = self._llm_extract(chunk, chunk_idx)
            except Exception as exc:
                msg = f"Chunk {chunk_idx} analysis error: {exc}"
                logger.warning("[Ingestion][%s] %s", self._run_id, msg)
                processing_notes.append(msg)
                # Fall back to mock extraction so partial results are preserved
                chunk_reqs = self._mock_extract(chunk, chunk_idx)

            all_requirements.extend(chunk_reqs)
            logger.debug(
                "[Ingestion][%s] Chunk %d: extracted %d requirement(s)",
                self._run_id,
                chunk_idx,
                len(chunk_reqs),
            )

        # ── Step 4: Deduplicate ──────────────────────────────────────────────
        original_count = len(all_requirements)
        all_requirements = self._deduplicate(all_requirements)
        if len(all_requirements) < original_count:
            note = (
                f"Deduplication removed {original_count - len(all_requirements)} "
                "near-duplicate requirements."
            )
            processing_notes.append(note)
            logger.info("[Ingestion][%s] %s", self._run_id, note)

        # ── Step 5: Assign sequential IDs ───────────────────────────────────
        for seq, req in enumerate(all_requirements, start=1):
            req.id = f"REQ-{seq:03d}"

        # ── Build output ─────────────────────────────────────────────────────
        self._emit_agent_completed(
            "ingestion_pipeline",
            output_preview=f"Extracted {len(all_requirements)} requirement(s) from {len(chunks)} chunk(s)",
        )
        output = IngestionOutput(
            requirements=all_requirements,
            document_name=document_name,
            total_requirements=len(all_requirements),
            chunks_processed=len(chunks),
            processing_notes=processing_notes,
        )

        self._emit(
            "log",
            {
                "message": (
                    f"Ingestion complete: {len(all_requirements)} requirement(s) "
                    f"extracted from {len(chunks)} chunk(s)"
                ),
                "level": "info",
            },
        )
        logger.info(
            "[Ingestion][%s] Done: %d requirements extracted from '%s'",
            self._run_id,
            len(all_requirements),
            document_name,
        )

        return output.model_dump()

    # ─────────────────────────────────────────────────────────────────────────
    # Private: LLM extraction
    # ─────────────────────────────────────────────────────────────────────────

    def _llm_extract(
        self,
        chunk: str,
        chunk_index: int,
    ) -> list[RequirementItem]:
        """
        Send *chunk* to the LLM and parse the returned JSON into RequirementItem objects.

        Resolution order for the LLM profile:
            1. Run-level profile (self._run_profile_id)
            2. Global default profile from DB (is_default=True)
            3. Environment-variable fallback (settings.DEFAULT_LLM_*)

        Falls back to :meth:`_mock_extract` on any LLM / JSON error.

        Args:
            chunk:       The text chunk to analyse.
            chunk_index: 1-based index, used for logging.

        Returns:
            List of :class:`RequirementItem` extracted from the chunk.
        """
        try:
            import litellm  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError("litellm is not installed. Run: uv add litellm") from exc

        profile = self._resolve_profile()
        if profile is None:
            logger.warning(
                "[Ingestion][%s] No LLM profile found — using mock extraction for chunk %d",
                self._run_id,
                chunk_index,
            )
            return self._mock_extract(chunk, chunk_index)

        try:
            model_string = get_model_string(str(profile.provider), str(profile.model))
        except ValueError as exc:
            logger.warning(
                "[Ingestion][%s] Invalid provider in LLM profile: %s — using mock extraction",
                self._run_id,
                exc,
            )
            return self._mock_extract(chunk, chunk_index)

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _USER_PROMPT_TEMPLATE.format(chunk=chunk),
            },
        ]

        call_kwargs: dict[str, Any] = {
            "model": model_string,
            "messages": messages,
            "temperature": float(profile.temperature),
            "max_tokens": int(profile.max_tokens),
        }

        # Attach credentials / endpoint if available
        api_key = getattr(profile, "api_key", None)
        if api_key:
            call_kwargs["api_key"] = api_key

        base_url = getattr(profile, "base_url", None)
        if base_url:
            call_kwargs["base_url"] = base_url
        elif str(profile.provider) == "ollama":
            call_kwargs["base_url"] = "http://localhost:11434"

        logger.debug(
            "[Ingestion][%s] LLM call — model=%s chunk_index=%d chunk_chars=%d",
            self._run_id,
            model_string,
            chunk_index,
            len(chunk),
        )

        response = litellm.completion(**call_kwargs)
        raw_content: str = (response.choices[0].message.content or "{}").strip()

        return self._parse_llm_response(raw_content, chunk, chunk_index)

    def _parse_llm_response(
        self,
        content: str,
        chunk: str,
        chunk_index: int,
    ) -> list[RequirementItem]:
        """
        Parse the raw LLM text response into RequirementItem objects.

        Handles common LLM response formatting issues:
        - Markdown code fences (```json ... ```)
        - Leading/trailing whitespace
        - Extra prose before/after the JSON block

        Args:
            content:     Raw LLM response string.
            chunk:       Original text chunk (used as raw_text in items).
            chunk_index: Chunk index for source tracking.

        Returns:
            List of :class:`RequirementItem` objects (may be empty).
        """
        # Strip markdown code fences if present
        content = _strip_code_fences(content)

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON from mixed prose + JSON responses
            data = _extract_json_from_text(content)
            if data is None:
                logger.warning(
                    "[Ingestion][%s] Chunk %d: LLM returned non-JSON content — "
                    "falling back to mock extraction.",
                    self._run_id,
                    chunk_index,
                )
                return self._mock_extract(chunk, chunk_index)

        requirements_raw = data.get("requirements", [])
        if not isinstance(requirements_raw, list):
            logger.warning(
                "[Ingestion][%s] Chunk %d: 'requirements' is not a list — ignoring.",
                self._run_id,
                chunk_index,
            )
            return []

        items: list[RequirementItem] = []
        raw_text_preview = chunk[:200]

        for raw in requirements_raw:
            if not isinstance(raw, dict):
                continue
            try:
                req_type_raw = str(raw.get("type", "functional")).lower()
                try:
                    req_type = RequirementType(req_type_raw)
                except ValueError:
                    req_type = RequirementType.FUNCTIONAL

                item = RequirementItem(
                    id="TBD",
                    title=str(raw.get("title") or "Untitled requirement")[:200],
                    description=str(raw.get("description") or ""),
                    type=req_type,
                    priority=str(raw.get("priority") or "medium").lower(),
                    tags=[str(t) for t in (raw.get("tags") or []) if t],
                    notes=str(raw.get("notes") or ""),
                    raw_text=raw_text_preview,
                    source_chunk=str(chunk_index),
                )
                items.append(item)
            except Exception as exc:
                logger.debug(
                    "[Ingestion][%s] Chunk %d: failed to parse requirement item: %s",
                    self._run_id,
                    chunk_index,
                    exc,
                )

        return items

    # ─────────────────────────────────────────────────────────────────────────
    # Private: Mock / heuristic extraction (fallback when LLM unavailable)
    # ─────────────────────────────────────────────────────────────────────────

    def _mock_extract(
        self,
        chunk: str,
        chunk_index: int,
    ) -> list[RequirementItem]:
        """
        Heuristic fallback that extracts candidate requirements without an LLM.

        Strategy:
        1. Look for lines that start with known requirement keywords
           (must, shall, should, the system, the application, …).
        2. Fall back to taking the first N non-trivial sentences if no
           keyword-prefixed lines are found.
        3. Return at most 5 candidates per chunk to avoid noise.

        This method is intentionally simple — it is only used when:
        - mock_mode=True is requested explicitly
        - LLM calls fail at runtime
        - No LLM profile is configured

        Args:
            chunk:       The text chunk to heuristically analyse.
            chunk_index: 1-based chunk index for source tracking.

        Returns:
            List of up to 5 :class:`RequirementItem` objects.
        """
        candidates: list[str] = []

        # Keyword patterns that suggest a requirement statement
        _REQ_PATTERNS = re.compile(
            r"(?i)^\s*(the system|the application|users?|admins?|the platform|it)"
            r"\s+(must|shall|should|will|can|cannot|need to|needs to|is required to)\b",
        )
        _MODAL_PATTERNS = re.compile(
            r"(?i)^\s*(must|shall|should|is required to|needs to)\b",
        )

        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        for line in lines:
            if len(line) < 20:
                continue
            if _REQ_PATTERNS.match(line) or _MODAL_PATTERNS.match(line):
                candidates.append(line)
            if len(candidates) >= 5:
                break

        # If keyword search yielded nothing, take the first substantive sentences
        if not candidates:
            sentences = re.split(r"(?<=[.!?])\s+", chunk.strip())
            for sentence in sentences:
                s = sentence.strip()
                if len(s) >= 30:
                    candidates.append(s)
                if len(candidates) >= 3:
                    break

        items: list[RequirementItem] = []
        for candidate in candidates:
            items.append(
                RequirementItem(
                    id="TBD",
                    title=candidate[:100],
                    description=candidate,
                    type=RequirementType.FUNCTIONAL,
                    priority="medium",
                    tags=["heuristic-extracted"],
                    notes="Extracted by heuristic fallback — verify manually.",
                    raw_text=candidate[:200],
                    source_chunk=str(chunk_index),
                )
            )

        return items

    # ─────────────────────────────────────────────────────────────────────────
    # Private: Deduplication
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _deduplicate(requirements: list[RequirementItem]) -> list[RequirementItem]:
        """
        Remove near-duplicate requirements based on normalised title similarity.

        Two requirements are considered duplicates if their normalised titles
        (lowercase, punctuation removed, max 60 chars) are identical.

        Args:
            requirements: Input list of RequirementItem objects (may contain dupes).

        Returns:
            Deduplicated list in the original order (first occurrence kept).
        """
        seen: set[str] = set()
        unique: list[RequirementItem] = []

        for req in requirements:
            normalised = _normalise_for_dedup(req.title)
            if normalised not in seen:
                seen.add(normalised)
                unique.append(req)

        return unique

    # ─────────────────────────────────────────────────────────────────────────
    # Private: LLM profile resolution
    # ─────────────────────────────────────────────────────────────────────────

    def _resolve_profile(self):
        """
        Resolve the LLM profile to use for ingestion analysis.

        Priority (consistent with AgentFactory override chain):
            1. Per-agent profile  (AgentConfig["ingestion_pipeline"].llm_profile)
            2. Run-level override (self._run_profile_id)
            3. Global default profile (is_default=True in DB)
            4. None  (caller falls back to mock extraction)

        Returns:
            An :class:`LLMProfile` ORM instance, or ``None`` if no profile is found.
        """
        # 1. Per-agent profile — cached after the first DB lookup
        if not self._per_agent_profile_checked:
            self._per_agent_profile_checked = True
            try:
                from sqlalchemy import select

                from app.db.models import AgentConfig

                stmt = select(AgentConfig).where(
                    AgentConfig.agent_id == "ingestion_pipeline"
                )
                cfg = self._db.scalar(stmt)
                if cfg is not None and cfg.llm_profile is not None:
                    self._per_agent_profile = cfg.llm_profile
                    logger.debug(
                        "[Ingestion][%s] Using per-agent LLM profile: %r",
                        self._run_id,
                        cfg.llm_profile.name,
                    )
            except Exception as exc:
                logger.warning(
                    "[Ingestion][%s] Failed to load per-agent profile: %s",
                    self._run_id,
                    exc,
                )

        if self._per_agent_profile is not None:
            return self._per_agent_profile

        # 2. Run-level override
        if self._run_profile_id is not None:
            from app.db.models import LLMProfile

            profile = self._db.get(LLMProfile, self._run_profile_id)
            if profile is not None:
                logger.debug(
                    "[Ingestion][%s] Using run-level LLM profile id=%d",
                    self._run_id,
                    self._run_profile_id,
                )
                return profile
            logger.warning(
                "[Ingestion][%s] Run profile id=%d not found — using global default.",
                self._run_id,
                self._run_profile_id,
            )

        # 3. Global default
        return self._llm_factory._load_default_profile()


# ─────────────────────────────────────────────────────────────────────────────
# Module-level helper utilities
# ─────────────────────────────────────────────────────────────────────────────


def _strip_code_fences(text: str) -> str:
    """
    Remove Markdown code fences from LLM output.

    Handles both:
      ```json          ```
      { ... }    and   { ... }
      ```              ```

    Args:
        text: Raw LLM response string.

    Returns:
        Text with code fences stripped, preserving the inner content.
    """
    text = text.strip()

    # Pattern: ```<optional_lang>\n...\n```
    fence_pattern = re.compile(r"^```[a-z]*\s*\n(.*)\n```\s*$", re.DOTALL)
    match = fence_pattern.match(text)
    if match:
        return match.group(1).strip()

    # Single-line fences (rare but happens)
    if text.startswith("```") and text.endswith("```") and len(text) > 6:
        inner = text[3:-3].strip()
        # Strip language identifier if present (e.g. "json\n{...")
        if "\n" in inner:
            first_line, rest = inner.split("\n", 1)
            if re.match(r"^[a-z]+$", first_line.strip()):
                return rest.strip()
        return inner

    return text


def _extract_json_from_text(text: str) -> dict | None:
    """
    Attempt to extract the first JSON object from mixed prose + JSON text.

    Useful when the LLM wraps the JSON in sentences like
    "Here is the JSON: {...}".

    Args:
        text: String that may contain a JSON object embedded in prose.

    Returns:
        Parsed dict if a JSON object is found, ``None`` otherwise.
    """
    # Find the first '{' and try progressive JSON parsing
    start = text.find("{")
    if start == -1:
        return None

    for end in range(len(text), start, -1):
        candidate = text[start:end]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    return None


def _normalise_for_dedup(title: str) -> str:
    """
    Normalise a requirement title for duplicate detection.

    Steps:
        1. Lowercase
        2. Remove punctuation and extra whitespace
        3. Truncate to first 60 characters

    Args:
        title: Raw requirement title string.

    Returns:
        Normalised comparison string.
    """
    lower = title.lower()
    no_punct = re.sub(r"[^\w\s]", "", lower)
    collapsed = re.sub(r"\s+", " ", no_punct).strip()
    return collapsed[:60]
