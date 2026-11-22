from uuid import uuid4

import pytest
from auto_at.contracts.vision import VisualCheckpoint
from auto_at.contracts.vision_coverage import VisualPageInventory
from domain.vision_coverage import inventory, remaining_observation, target_key
from test_codex_candidate_service import bound_observation


def checkpoint():
    return VisualCheckpoint(id=uuid4(), state_id=uuid4(), url_fingerprint="a" * 64,
                            semantic_fingerprint="b" * 64, scroll_x=0, scroll_y=0,
                            page_url="https://fixture.test/news")


def test_completed_control_excluded_even_with_fresh_element_ids():
    bound, page = bound_observation(), checkpoint()
    descriptor = bound.bindings[0].descriptor
    operation = uuid4()
    attempted = {target_key(page, descriptor): {"status": "completed", "operation_id": operation}}
    fresh_id = "e_" + "b" * 32
    fresh = bound.model_copy(update={
        "observation": bound.observation.model_copy(update={"elements": (
            bound.observation.elements[0].model_copy(update={"element_id": fresh_id}),
        )}),
        "bindings": (bound.bindings[0].model_copy(update={"element_id": fresh_id}),),
    })
    assert remaining_observation(page, fresh, attempted).observation.elements == ()
    saved = inventory(page, fresh, attempted)
    assert saved.page_url == "https://fixture.test/news"
    assert saved.controls[0].status == "completed"
    assert saved.controls[0].operation_id == operation
    # The same navigation control on a different URL remains eligible.
    other = page.model_copy(update={"url_fingerprint": "c" * 64})
    assert len(remaining_observation(other, fresh, attempted).observation.elements) == 1


def test_inventory_keeps_pending_controls_and_partial_coverage():
    bound = bound_observation()
    bound = bound.model_copy(update={"observation": bound.observation.model_copy(update={
        "scrollable": True, "truncated": True, "skipped_count": 3,
    })})
    saved = inventory(checkpoint(), bound, {})
    assert saved.controls[0].status == "pending"
    assert saved.scrollable and saved.truncated and saved.skipped_count == 3
    assert VisualPageInventory.model_validate_json(saved.model_dump_json()) == saved


@pytest.mark.parametrize("url", ["javascript:alert(1)", "https://u:p@fixture.test/",
                                "https://fixture.test/?token=private", "https://fixture.test/#secret"])
def test_checkpoint_refuses_non_redacted_or_unsafe_page_urls(url):
    with pytest.raises(ValueError):
        VisualCheckpoint.model_validate(checkpoint().model_dump() | {"page_url": url})
