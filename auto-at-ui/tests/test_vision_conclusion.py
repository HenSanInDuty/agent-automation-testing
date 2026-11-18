from types import SimpleNamespace as Item

import pytest
from domain.vision_conclusion import exploration_conclusion


def conclude(*, state="completed", pages=None, operations=None, candidates=0, legacy=False):
    return exploration_conclusion(
        state=state, pages=pages if pages is not None else [page()],
        operations=operations if operations is not None else [operation()],
        candidates_not_attempted=candidates, legacy=legacy,
    )


def operation(**changes):
    return Item(**(dict(id="click", status="completed", purpose="explore", action_kind="click")
                   | changes))


def page(**changes):
    return Item(**(dict(url_fingerprint="url-a", interaction_scope="buttons",
                       truncated=False, skipped_count=0, scrollable=True,
                       controls=[Item(key="button-a", status="completed", operation_id="click")])
                   | changes))


def test_conclusion_deduplicates_snapshots_but_not_different_urls():
    result = conclude(pages=[page(), page(), page(url_fingerprint="url-b")])
    assert result["status"] == "completed"
    assert result["observed_controls"] == result["completed_controls"] == 2
    assert result["operations_completed"] == 1
    assert result["remaining_controls"] == 0
    assert result["business_outcome"] == "unverified"
    assert result["coverage"] == "observed_controls_completed"


@pytest.mark.parametrize("status", ["failed", "rejected", "unknown", "prepared", "executing"])
def test_setup_or_restore_errors_prevent_clean_conclusion(status):
    result = conclude(operations=[operation(), operation(id="restore", purpose="restore",
                                                       action_kind="scroll", status=status)])
    assert result["status"] == "partial"
    field = status if status in {"failed", "rejected", "unknown"} else "pending"
    assert result[f"operations_{field}"] == 1
    assert result["completed_controls"] == 1


@pytest.mark.parametrize("state,expected", [("running", "in_progress"),
                                          ("queued", "in_progress"),
                                          ("cancelled", "cancelled"),
                                          ("unavailable", "partial")])
def test_terminal_status_is_not_inferred_from_successful_clicks(state, expected):
    assert conclude(state=state)["status"] == expected


@pytest.mark.parametrize("changes", [{"skipped_count": 1}, {"truncated": True}])
def test_limited_inventory_cannot_claim_complete_coverage(changes):
    result = conclude(pages=[page(**changes)])
    assert result["status"] == "partial" and result["inventory_limited"]


def test_legacy_missing_and_empty_inventories_never_claim_all_controls_work():
    for changes in ({"legacy": True}, {"pages": []}):
        result = conclude(**changes)
        assert result["status"] == "partial"
        assert result["observed_controls"] is None
        assert result["completed_controls"] is None
    assert conclude(pages=[page(controls=[])])["status"] == "partial"


def test_completed_inventory_requires_a_matching_completed_exploration_operation():
    for operations in ([], [operation(id="different")], [operation(purpose="restore")]):
        result = conclude(operations=operations)
        assert result["remaining_controls"] == 1
        assert result["status"] == "partial"
    assert conclude(candidates=1)["status"] == "partial"


def test_pending_control_does_not_overwrite_a_completed_snapshot():
    pending = page(controls=[Item(key="button-a", status="queued", operation_id=None)])
    assert conclude(pages=[page(), pending])["completed_controls"] == 1
    assert conclude(pages=[pending])["remaining_controls"] == 1
