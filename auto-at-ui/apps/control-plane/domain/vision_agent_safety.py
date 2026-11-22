"""Pure, code-enforced guard rails for browser-agent actions (layer one; worker is layer two)."""

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from auto_at.contracts.generation import WILDCARD_ORIGIN
from auto_at.contracts.vision import validate_locator_value

AGENT_ACTION_KINDS = frozenset({
    "click", "type", "scroll", "wait", "back", "close_popup", "navigate",
})
# The only actions accepted on a page outside the project allowlist (K3).
LEAVING_ACTIONS = frozenset({"close_popup", "back"})
BLOCKED_INPUT_TYPES = frozenset({"submit", "reset"})

# One source for the worker too (`VisualWorkerOpen.blocked_action_terms`). The worker lowercases and
# NFC-normalizes but does not strip diacritics, so each Vietnamese term lists its accented and
# unaccented spelling. "đăng ký" and "nạp thẻ" are deliberately absent (the benchmark needs them).
BLOCKED_ACTION_TERMS: tuple[str, ...] = (
    "đăng xuất", "dang xuat", "xóa", "xoá", "xoa", "thanh toán", "thanh toan",
    "đặt hàng", "dat hang", "mua ngay", "mua hàng", "mua hang", "gửi", "gui di",
    "xác nhận", "xac nhan",
    "submit", "delete", "remove", "logout", "log out", "sign out", "signout", "payment",
    "pay now", "purchase", "checkout", "place order", "buy now", "unsubscribe", "send",
)

_D_BAR = str.maketrans({"đ": "d", "Đ": "D"})


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str | None = None


def _fold(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def _plain(value: str) -> str:
    """Lowercase without diacritics, so an unaccented term also matches accented page text."""
    decomposed = unicodedata.normalize("NFD", value.translate(_D_BAR)).casefold()
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def blocked_term(name: str) -> str | None:
    folded, plain = _fold(name), _plain(name)
    return next((term for term in BLOCKED_ACTION_TERMS
                 if term in folded or (_plain(term) == term and term in plain)), None)


def origin_allowed(page_origin: str | None, allowed_origins: Sequence[str]) -> bool:
    """An unknown origin (non-HTTP page, missing URL) is not allowed: fail closed."""
    return page_origin is not None and (
        WILDCARD_ORIGIN in allowed_origins or page_origin in allowed_origins
    )


def _unsafe_text(text: str) -> bool:
    if "\r" in text or "\n" in text:
        return True
    try:
        validate_locator_value(text)
    except ValueError:
        return True
    return False


def check_action(action, element, page_origin: str | None,
                 allowed_origins: Sequence[str]) -> Decision:
    """Decide before any worker request. `element` is the `CodexDomElement` a ref resolved to."""
    if action.kind not in AGENT_ACTION_KINDS:
        return Decision(False, "action_kind_blocked")
    if action.kind not in LEAVING_ACTIONS and not origin_allowed(page_origin, allowed_origins):
        return Decision(False, "origin_blocked")
    if action.kind == "type" and _unsafe_text(action.text or ""):
        return Decision(False, "sensitive_action_blocked")
    if element is not None and action.kind in {"click", "type"}:
        if element.input_type in BLOCKED_INPUT_TYPES or blocked_term(element.name):
            return Decision(False, "sensitive_action_blocked")
        if not element.enabled or (action.kind == "type" and not element.editable):
            return Decision(False, "ineligible_target")
    return Decision(True)
