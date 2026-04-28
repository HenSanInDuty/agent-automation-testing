"""
tools/text_chunker.py
─────────────────────
Splits long document text into overlapping chunks suitable for LLM processing.

Features:
  - Sentence-boundary-aware splitting (avoids cutting mid-sentence)
  - Configurable chunk size and overlap
  - Paragraph-first strategy (prefers splitting at double-newlines)
  - TextChunk dataclass with positional metadata
  - Pure Python — no external dependencies

Usage::

    from app.tools.text_chunker import chunk_text, chunk_text_rich

    chunks = chunk_text(raw_text, chunk_size=2000, overlap=200)

    rich = chunk_text_rich(raw_text, chunk_size=2000, overlap=200)
    for c in rich:
        print(c.chunk_index, c.char_start, c.length)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Data class
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class TextChunk:
    """A single text chunk with positional metadata."""

    text: str
    chunk_index: int
    char_start: int
    char_end: int
    word_count: int = field(init=False)
    sentence_count: int = field(init=False)

    def __post_init__(self) -> None:
        self.word_count = len(self.text.split())
        self.sentence_count = len(_split_sentences(self.text))

    @property
    def length(self) -> int:
        return len(self.text)

    def __repr__(self) -> str:
        return (
            f"TextChunk(index={self.chunk_index}, "
            f"chars={self.char_start}-{self.char_end}, "
            f"words={self.word_count})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


def chunk_text(
    text: str,
    chunk_size: int = 2000,
    overlap: int = 200,
    min_chunk_size: int = 50,
) -> list[str]:
    """
    Split *text* into overlapping chunks of approximately *chunk_size* characters.

    Strategy (highest → lowest preference for split point):
      1. Double-newline  (paragraph boundary)
      2. Single-newline  (line boundary)
      3. Sentence-ending punctuation  (. ! ?)
      4. Space           (word boundary)
      5. Hard cut        (last resort)

    Args:
        text:           Input text to chunk.
        chunk_size:     Target chunk size in characters.
        overlap:        Number of characters to carry over into the next chunk.
                        Must be < chunk_size.
        min_chunk_size: Chunks shorter than this are dropped (avoids tiny tails).

    Returns:
        List of text strings.  May be empty if *text* is blank.

    Raises:
        ValueError: If overlap >= chunk_size.
    """
    if overlap >= chunk_size:
        raise ValueError(
            f"overlap ({overlap}) must be less than chunk_size ({chunk_size})."
        )

    text = text.strip()
    if not text:
        return []

    # Short enough to fit in a single chunk
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))

        if end >= len(text):
            # Final tail — include everything
            tail = text[start:].strip()
            if len(tail) >= min_chunk_size:
                chunks.append(tail)
            break

        # Find a graceful split point near *end*
        split = _find_split_point(text, end, look_back=min(300, chunk_size // 2))
        chunk = text[start:split].strip()

        if len(chunk) >= min_chunk_size:
            chunks.append(chunk)

        # Advance start with overlap
        next_start = split - overlap
        if next_start <= start:
            # Safety: always move forward at least 1 character
            next_start = start + max(1, chunk_size - overlap)

        start = next_start

    logger.debug(
        "chunk_text: input=%d chars → %d chunks (size=%d, overlap=%d, min=%d)",
        len(text),
        len(chunks),
        chunk_size,
        overlap,
        min_chunk_size,
    )
    return chunks


def chunk_text_rich(
    text: str,
    chunk_size: int = 2000,
    overlap: int = 200,
    min_chunk_size: int = 50,
) -> list[TextChunk]:
    """
    Like :func:`chunk_text` but returns :class:`TextChunk` objects that include
    character-position metadata useful for provenance tracking.

    Returns:
        List of :class:`TextChunk` instances ordered by chunk_index.
    """
    raw_chunks = chunk_text(text, chunk_size, overlap, min_chunk_size)
    result: list[TextChunk] = []
    search_from = 0

    for idx, chunk_str in enumerate(raw_chunks):
        # Locate the chunk in the original text.  We search from the position
        # of the previous chunk to avoid false positives.
        prefix = chunk_str[:60]  # Use first 60 chars as anchor
        char_start = text.find(prefix, search_from)
        if char_start == -1:
            # Fallback: try the full string
            char_start = text.find(chunk_str[:30], search_from)
        if char_start == -1:
            char_start = search_from

        char_end = char_start + len(chunk_str)
        result.append(
            TextChunk(
                text=chunk_str,
                chunk_index=idx,
                char_start=char_start,
                char_end=char_end,
            )
        )
        # Next search starts slightly before the end to accommodate overlap
        search_from = max(0, char_end - overlap)

    return result


def estimate_token_count(text: str, chars_per_token: float = 4.0) -> int:
    """
    Rough estimate of token count using character-to-token ratio.

    GPT-4 / most modern LLMs average ~4 chars/token for English text.

    Args:
        text:             Input text.
        chars_per_token:  Average characters per token (default 4.0).

    Returns:
        Estimated integer token count.
    """
    return max(1, int(len(text) / chars_per_token))


def chunk_by_tokens(
    text: str,
    max_tokens: int = 512,
    overlap_tokens: int = 50,
    chars_per_token: float = 4.0,
) -> list[str]:
    """
    Convenience wrapper that converts token limits to character limits and
    delegates to :func:`chunk_text`.

    Args:
        text:             Input text.
        max_tokens:       Target chunk size in tokens.
        overlap_tokens:   Overlap size in tokens.
        chars_per_token:  Conversion factor.

    Returns:
        List of text strings.
    """
    chunk_size = int(max_tokens * chars_per_token)
    overlap = int(overlap_tokens * chars_per_token)
    return chunk_text(text, chunk_size=chunk_size, overlap=overlap)


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

# Sentence-ending pattern: period/!/?  not preceded by common abbreviations
_SENTENCE_END = re.compile(r"(?<![A-Z][a-z]\.)(?<=\.|\!|\?)\s")

# Paragraph boundary pattern
_PARA_BREAK = re.compile(r"\n\s*\n")


def _find_split_point(text: str, near: int, look_back: int = 300) -> int:
    """
    Return the best character position to split *text* close to *near*.

    Searches *look_back* characters before *near* for (in order of preference):
      1. Paragraph boundary  (\n\n or \n followed by whitespace)
      2. Sentence boundary   (. ! ?)
      3. Line boundary       (\n)
      4. Word boundary       (space)
      5. Exact position      (last resort)

    Args:
        text:      Full source text.
        near:      Target split position.
        look_back: How far back to search.

    Returns:
        Best split position (exclusive end of the left chunk).
    """
    window_start = max(0, near - look_back)
    segment = text[window_start:near]

    # 1. Paragraph boundary
    for match in reversed(list(_PARA_BREAK.finditer(segment))):
        return window_start + match.end()

    # 2. Sentence boundary
    for match in reversed(list(_SENTENCE_END.finditer(segment))):
        return window_start + match.end()

    # 3. Sentence-end punctuation without following space
    for punct in (".\n", "!\n", "?\n", ".", "!", "?"):
        pos = segment.rfind(punct)
        if pos != -1:
            return window_start + pos + len(punct)

    # 4. Line boundary
    pos = segment.rfind("\n")
    if pos != -1:
        return window_start + pos + 1

    # 5. Word boundary
    pos = segment.rfind(" ")
    if pos != -1:
        return window_start + pos + 1

    # 6. Hard cut
    return near


def _split_sentences(text: str) -> list[str]:
    """
    Naive sentence splitter used only for metadata counting in TextChunk.
    Not intended for production NLP use.
    """
    # Split on .  !  ? followed by whitespace or end-of-string
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p]
