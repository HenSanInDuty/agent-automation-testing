"""ADR-047 (phase 10): assertion candidates the controller verifies, never the model.

The agent writes quotes in the `evidence` of a `met` check. A quote becomes a candidate only when
it equals text the session itself observed (page text or a control name, both already filtered by
the worker and by `validate_locator_value`) or sits inside one page-text item. The expected text
therefore always comes from the page, not from the model. Pure functions, no I/O.
"""

import re
from collections.abc import Sequence

# Same cap as the worker's page text (`PAGE_TEXT_MAX_CHARS`, codex_bridge.py:127).
CANDIDATE_MAX_CHARS = 160
# What the controller remembers per session (memory only, never stored).
OBSERVED_MAX_ITEMS = 200
# Same cap as the trace contract (`VERIFIED_TEXT_ITEMS_MAX`); a candidate over it counts as dropped.
VERIFIED_ITEMS_MAX = 100
CONTROL_KIND = "control_name"
# ponytail: a quote shorter than this may only match a whole observed item, never a fragment of
# a paragraph, or `'a'` would "verify" against any sentence. Raise it if real runs show noise.
FRAGMENT_MIN_CHARS = 2

_QUOTED = (
    re.compile(r'"([^"]+)"'),
    re.compile(r"“([^”]+)”"),
    # A single quote counts only when it is not an apostrophe inside a word ("don't").
    re.compile(r"(?<!\w)'([^']+)'(?!\w)"),
)


def squash(text: str) -> str:
    """Whitespace collapsed to single spaces, case kept (split idiom of vision_scope.py:8)."""
    return " ".join(text.split())


class ObservedText:
    """Bounded set of (kind, text) the session saw; field values are never added."""

    def __init__(self, limit: int = OBSERVED_MAX_ITEMS):
        self.limit = limit
        self.items: dict[tuple[str, str], None] = {}
        self.truncated = False

    def _add(self, kind: str, text: str) -> None:
        text = squash(text)
        if not text or (kind, text) in self.items:
            return
        if len(self.items) >= self.limit:
            self.truncated = True
            return
        self.items[(kind, text)] = None

    def add(self, observation) -> None:
        """Page text and control names of one observation; an old one without page text is fine."""
        for item in getattr(observation, "page_text", ()) or ():
            self._add(item.kind, item.text)
        for element in getattr(observation, "elements", ()) or ():
            self._add(CONTROL_KIND, element.name or "")


def quoted_segments(text: str) -> list[str]:
    """Quoted parts of `text` in order of appearance, whitespace collapsed, duplicates removed."""
    found = sorted(
        (match.start(), squash(match.group(1)))
        for pattern in _QUOTED for match in pattern.finditer(text)
    )
    return [*dict.fromkeys(segment for _, segment in found if segment)]


def _kind_of(segment: str, observed: ObservedText) -> str | None:
    if len(segment) > CANDIDATE_MAX_CHARS:
        return None
    for kind, text in observed.items:
        if text == segment:
            return kind
    if len(segment) >= FRAGMENT_MIN_CHARS:
        for kind, text in observed.items:
            if kind != CONTROL_KIND and segment in text:
                return kind
    return None


def _overlaps(candidate: str, typed: str) -> bool:
    """One of the two texts is the other or sits inside it (case ignored, whitespace collapsed).

    A part shorter than `FRAGMENT_MIN_CHARS` only counts as a whole match, the same rule as
    `_kind_of`, so a typed `"a"` does not mark every sentence that has an `a` in it.
    """
    candidate, typed = squash(candidate).casefold(), squash(typed).casefold()
    if not candidate or not typed:
        return False
    if candidate == typed:
        return True
    shorter, longer = sorted((candidate, typed), key=len)
    return len(shorter) >= FRAGMENT_MIN_CHARS and shorter in longer


def derived_from_typed(text: str, typed: Sequence[str]) -> bool:
    """True when `text` holds, or is part of, a value the agent typed in the session (F5).

    The requester may later type another value, so such a candidate would stop matching the page.
    The typed values are only compared here, in memory; they are never stored or returned.
    """
    return any(_overlaps(text, value) for value in typed)


def verify_quotes(checks, observed: ObservedText, typed: Sequence[str] = ()) -> dict:
    """Candidates from the `met` checks only.

    -> {"items": [{"kind", "text", "check_index"[, "derived_from_typed": True]}],
        "dropped": n, "truncated": bool}
    `dropped` counts quotes that matched nothing observed; `truncated` says the observed set hit
    its cap, so a missing candidate may only mean the text was never remembered.
    `typed` are the values the agent typed in the session: an item that holds one gets
    `derived_from_typed: True` (key absent otherwise, so a session without typed text keeps the
    exact stored shape and trace hash it had before phase 17).
    """
    items, dropped = [], 0
    for index, check in enumerate(checks):
        if check.status != "met":
            continue
        for segment in dict.fromkeys(
            [*quoted_segments(check.evidence), *quoted_segments(check.expectation)]
        ):
            kind = _kind_of(segment, observed)
            if kind is None or len(items) >= VERIFIED_ITEMS_MAX:
                dropped += 1
            else:
                item = {"kind": kind, "text": segment, "check_index": index}
                if derived_from_typed(segment, typed):
                    item["derived_from_typed"] = True
                items.append(item)
    return {"items": items, "dropped": dropped, "truncated": observed.truncated}
