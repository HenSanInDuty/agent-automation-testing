"""Decision table for the control-plane (layer one) agent action guard."""

import json
import unicodedata
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from auto_at.contracts.codex_bridge import AgentAction, CodexDomElement
from auto_at.contracts.vision_worker import VisualWorkerOpen
from domain.vision_agent_safety import (
    BLOCKED_ACTION_TERMS,
    Decision,
    blocked_term,
    check_action,
    origin_allowed,
)

ORACLE = Path(__file__).parents[1] / "benchmark/vision/accuracy/oracle-mongchiton-1280-v1.json"
ALLOWED = ["https://app.test"]
HERE = "https://app.test"


def element(name="Details", **overrides):
    return CodexDomElement.model_validate(
        {"element_id": "e_" + "a" * 32, "role": "button", "name": name, "enabled": True,
         "editable": False, **overrides}
    )


def click(ref="1:1"):
    return AgentAction(kind="click", ref=ref)


def type_(text="hello", ref="1:1"):
    return AgentAction(kind="type", ref=ref, text=text)


def test_plain_click_on_allowed_origin_is_allowed():
    assert check_action(click(), element(), HERE, ALLOWED) == Decision(True)


@pytest.mark.parametrize("kind", ["scroll", "wait", "navigate", "click", "type"])
def test_every_kind_but_leaving_ones_is_blocked_on_a_page_outside_the_allowlist(kind):
    action = {
        "click": click(), "type": type_(), "scroll": AgentAction(kind="scroll", delta_y=300),
        "wait": AgentAction(kind="wait", duration_ms=100), "navigate": AgentAction(kind="navigate"),
    }[kind]
    decision = check_action(action, element(editable=True), "https://other.test", ALLOWED)
    assert decision == Decision(False, "origin_blocked")


@pytest.mark.parametrize("kind", ["back", "close_popup"])
def test_leaving_actions_run_on_a_page_outside_the_allowlist(kind):
    assert check_action(AgentAction(kind=kind), None, "https://other.test", ALLOWED).allowed


def test_unknown_origin_fails_closed_but_leaving_still_works():
    assert check_action(click(), element(), None, ALLOWED) == Decision(False, "origin_blocked")
    assert check_action(AgentAction(kind="back"), None, None, ALLOWED).allowed


def test_wildcard_allowlist_admits_any_known_origin_but_not_an_unknown_one():
    assert origin_allowed("https://anything.test", ["*"])
    assert not origin_allowed(None, ["*"])
    assert not origin_allowed("https://x.test", [])


def test_kind_outside_the_seven_is_blocked_before_anything_else():
    action = SimpleNamespace(kind="press_key", text=None)
    assert check_action(action, None, HERE, ALLOWED) == Decision(False, "action_kind_blocked")
    assert check_action(action, None, "https://other.test", ALLOWED).reason == "action_kind_blocked"


@pytest.mark.parametrize("input_type", ["submit", "reset"])
def test_submit_and_reset_inputs_are_blocked(input_type):
    decision = check_action(click(), element("OK", input_type=input_type), HERE, ALLOWED)
    assert decision == Decision(False, "sensitive_action_blocked")


@pytest.mark.parametrize("name", [
    "Delete account", "DELETE", "Xóa tài khoản", "XOÁ", "xoa tai khoan", "Đăng xuất",
    "ĐĂNG XUẤT", "dang xuat", "Thanh toán ngay", "THANH TOAN", "Mua ngay", "Gửi đi", "Sign Out",
    "Log out", "Place order", "Xác nhận", "xac nhan",
])
def test_sensitive_names_are_blocked_in_any_case_and_with_or_without_diacritics(name):
    assert check_action(click(), element(name), HERE, ALLOWED) == Decision(
        False, "sensitive_action_blocked"
    )


@pytest.mark.parametrize("form", ["NFC", "NFD", "NFKD"])
def test_decomposed_unicode_names_match_the_same_terms(form):
    name = unicodedata.normalize(form, "Xóa tài khoản")
    assert blocked_term(name) is not None
    assert blocked_term(unicodedata.normalize(form, "ĐĂNG XUẤT")) is not None


@pytest.mark.parametrize("name", ["ĐĂNG KÝ", "Đăng ký", "dang ky", "NẠP THẺ", "Nạp thẻ", "nap the"])
def test_registration_and_top_up_controls_are_not_blocked(name):
    assert check_action(click(), element(name), HERE, ALLOWED) == Decision(True)


def test_term_list_carries_both_spellings_for_the_worker_which_does_not_strip_diacritics():
    for accented, plain in [("đăng xuất", "dang xuat"), ("thanh toán", "thanh toan"),
                            ("xóa", "xoa"), ("xác nhận", "xac nhan")]:
        assert accented in BLOCKED_ACTION_TERMS and plain in BLOCKED_ACTION_TERMS
    assert all(term == unicodedata.normalize("NFC", term).casefold()
               for term in BLOCKED_ACTION_TERMS)
    assert not {"đăng ký", "dang ky", "nạp thẻ", "nap the"} & set(BLOCKED_ACTION_TERMS)


def test_term_list_fits_the_worker_open_contract():
    open_request = VisualWorkerOpen(
        tenant_id="t", project_id=uuid4(), session_id=uuid4(), fencing_token=1,
        target_url="https://app.test/", allowed_origins=tuple(ALLOWED),
        deadline="2030-01-01T00:00:00+00:00", max_session_seconds=60, max_states=2, max_hops=2,
        max_screenshot_bytes=2048, agent_mode=True, blocked_action_terms=BLOCKED_ACTION_TERMS,
    )
    assert open_request.blocked_action_terms == BLOCKED_ACTION_TERMS


@pytest.mark.parametrize("text", ["line\nbreak", "a\r\nb", "x\ry"])
def test_type_text_with_a_line_break_is_never_sent(text):
    assert check_action(type_(text), element(editable=True), HERE, ALLOWED) == Decision(
        False, "sensitive_action_blocked"
    )


@pytest.mark.parametrize("text", ["password: hunter2", "me@example.com", "1234567890", " padded"])
def test_type_text_with_secrets_or_identities_is_blocked(text):
    decision = check_action(type_(text), element(editable=True), HERE, ALLOWED)
    assert decision == Decision(False, "sensitive_action_blocked")


def test_type_text_without_line_break_into_an_editable_field_is_allowed():
    field = element("Search", editable=True)
    assert check_action(type_("sample text"), field, HERE, ALLOWED).allowed


def test_disabled_and_non_editable_targets_are_ineligible_without_a_worker_call():
    assert check_action(click(), element(enabled=False), HERE, ALLOWED) == Decision(
        False, "ineligible_target"
    )
    decision = check_action(type_(), element(editable=False), HERE, ALLOWED)
    assert decision.reason == "ineligible_target"


def test_origin_is_checked_before_the_element_rules():
    decision = check_action(click(), element("Delete"), "https://other.test", ALLOWED)
    assert decision.reason == "origin_blocked"


def oracle_labels():
    data = json.loads(ORACLE.read_text(encoding="utf-8"))
    return [(item["id"], item["label"]) for item in data["examples"] if item["expected"]]


def test_oracle_positive_labels_are_never_blocked():
    items = oracle_labels()
    assert len(items) >= 20
    blocked = [(ident, label) for ident, label in items
               if not check_action(click(), element(label[:120]), HERE, ALLOWED).allowed]
    assert blocked == []
