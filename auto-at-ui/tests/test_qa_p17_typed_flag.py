"""QA phase 17: independent edge checks for the `derived_from_typed` flag (F5).

Pure (no database, no model, no stack). Complements the developer tests: the overlap rule at its
edges, the stored shape of old sessions, the contract hash, and the renderer's use of the flag.
"""

import hashlib
import json
import unicodedata

import pytest
from application.agent_task_renderer import render_agent_task_source
from application.vision_source_renderer import literal
from auto_at.contracts.agent_task_trace import AgentTaskAssessmentCopy, VerifiedTextItem
from domain.verified_text import derived_from_typed, verify_quotes
from test_agent_task_renderer import clicked, final_lines, trace_of, typed
from test_vision_verified_text import check, observation, seen_of

# ------------------------------------------------------------------ overlap rule, edges


@pytest.mark.parametrize(
    ("text", "values", "expected"),
    [
        ("hoàn thành: Viết báo cáo", ["VIẾT BÁO CÁO"], True),  # Vietnamese upper case
        ("Đăng nhập thành công", ["đăng nhập"], True),  # Đ / đ casefold
        ("a", ["a"], True),  # one char, whole match
        ("a lot of items", ["a"], False),  # one char never marks a sentence
        ("ok", ["ok"], True),  # two chars, whole match
        ("book list", ["ok"], True),  # a two-char fragment does count
        ("Xin chào", ["  xin   chào "], True),  # whitespace collapsed on both sides
        ("Xin chào", ["   "], False),  # whitespace-only typed value
        ("Xin chào", [""], False),
        ("Xin chào", [], False),
        ("", ["abc"], False),
        ("Xin chào, demo", ["Demo1234"], False),  # the typed value is longer, not a part of it
        ("x" * 160, ["x" * 3], True),  # a very long candidate
        ("Balo laptop - 310.000 đ", ["balo"], True),
    ],
)
def test_overlap_edges(text, values, expected):
    assert derived_from_typed(text, values) is expected


def test_typed_value_in_nfd_form_is_not_matched_known_gap():
    """Known gap, safe side only if the page also uses NFD: the rule does not normalise Unicode.

    Pinned so a later normalisation flips this test instead of going unnoticed.
    """
    candidate = unicodedata.normalize("NFC", "Viết báo cáo")
    typed_value = unicodedata.normalize("NFD", "Viết báo cáo")
    assert candidate != typed_value
    assert derived_from_typed(candidate, [typed_value]) is False


def test_verify_quotes_never_returns_the_typed_value_itself():
    result = verify_quotes(
        [check('status "Saved"')], seen_of(observation([("status", "Saved")])), ["SECRET-VALUE-9"]
    )
    assert "SECRET-VALUE-9" not in json.dumps(result)
    assert result["items"] == [{"kind": "status", "text": "Saved", "check_index": 0}]


# ------------------------------------------------------------------ contract: old sessions and hash


def test_the_flag_is_absent_from_the_dump_when_false_and_present_when_true():
    plain = VerifiedTextItem(kind="status", text="x", check_index=0)
    assert plain.derived_from_typed is False
    assert "derived_from_typed" not in plain.model_dump()
    assert "derived_from_typed" not in plain.model_dump_json()
    explicit_false = VerifiedTextItem(
        kind="status", text="x", check_index=0, derived_from_typed=False
    )
    assert explicit_false.model_dump() == plain.model_dump()
    flagged = VerifiedTextItem(kind="status", text="x", check_index=0, derived_from_typed=True)
    assert flagged.model_dump()["derived_from_typed"] is True


def test_an_old_stored_assessment_reads_and_hashes_like_phase_16():
    old = {
        "schema_version": "v1", "status": "achieved", "summary": "Did the task.",
        "checks": [{"expectation": "Result shown", "status": "met", "evidence": "'x'"}],
        "source": "agent", "stop_reason": "agent_done",
        "facts": {"actions_completed": 1, "actions_failed": 0, "actions_blocked_or_skipped": 0},
        "advisory": True,
        "verified_text": {"items": [{"kind": "status", "text": "Hi", "check_index": 0}],
                          "dropped": 0, "truncated": False},
    }
    copy = AgentTaskAssessmentCopy.model_validate(old)
    assert copy.verified_text.items[0].derived_from_typed is False
    # the dump equals the stored payload, so any hash over the dump equals the phase 16 hash
    assert copy.model_dump(mode="json") == old
    canonical = json.dumps(copy.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    assert canonical == json.dumps(old, sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(canonical.encode()).hexdigest()


def test_a_trace_with_a_flag_hashes_differently_from_the_unflagged_one():
    steps = [typed(1, "Name", 4), clicked(1, "Go")]
    assert (trace_of(steps, [("status", "Hi", True)]).trace_hash
            != trace_of(steps, [("status", "Hi")]).trace_hash)


# ------------------------------------------------------------------ renderer


def test_flagged_candidates_are_left_out_clean_ones_still_assert_and_the_note_names_no_text():
    trace = trace_of(
        [typed(1, "Việc mới", 12), clicked(1, "Thêm")],
        [("status", "hoàn thành: Viết báo cáo", True), ("heading", "Danh sách việc"),
         ("control_name", "Thêm")],
        target_url="http://task-target:7300/todos",
    )
    output = render_agent_task_source(trace, ["Giá trị khác"])
    source = output.playwright_test_source
    for text in ("hoàn thành: Viết báo cáo", "Viết báo cáo"):
        assert literal(text) not in source and text not in source
    assert literal("Danh sách việc") in source  # the clean candidate is still asserted
    assert len(final_lines(output)) == 2
    notes = " ".join(output.stop_conditions)
    assert "1 candidate(s) were left out" in notes
    assert "Viết báo cáo" not in notes and "Giá trị khác" not in notes
    assert all("Viết báo cáo" not in a for a in output.assumptions)


def test_without_any_flag_the_renderer_adds_no_typed_note():
    trace = trace_of([typed(1, "Name", 4), clicked(1, "Go")], [("heading", "Done")])
    output = render_agent_task_source(trace, ["abcd"])
    assert not any("typed in the session" in n for n in output.stop_conditions)
