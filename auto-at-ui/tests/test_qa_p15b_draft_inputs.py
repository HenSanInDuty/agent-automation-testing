"""QA phase 15b: edge cases for `GET .../test-draft/inputs` beyond the developer's tests.

Reuses the developer's in-memory `World`, `Rows` and route fixture; no product code is touched.
"""

from test_agent_task_draft import World
from test_agent_task_draft_inputs import api, read  # noqa: F401
from test_agent_task_trace import Rows


def _rows(*type_steps):
    """type_steps: (locator_name, typed text, step_index); one click closes each step."""
    rows = Rows()
    rows.op("navigate", purpose="setup")
    by_step: dict[int, list] = {}
    for name, text, step in type_steps:
        by_step.setdefault(step, []).append(rows.op("type", name=name, text=text))
    for step, ops in by_step.items():
        ops.append(rows.op("click", name=f"Go {step}"))
        rows.step(step, *ops)
    return rows


def test_qa15b_lengths_count_characters_not_bytes_and_post_accepts_exactly_those():
    rows = _rows(("Tên", "Nguyễn Văn Ắ", 1), ("Mã", "x" * 500, 1), ("Ghi chú", "😀é", 2))
    world = World(rows)
    result = read(world)
    chars = [item[2] for item in result.type_steps]
    assert chars == [len("Nguyễn Văn Ắ"), 500, len("😀é")]
    values = ["a" * n for n in chars]
    assert world.create(values).created is True  # POST agrees with GET about the count


def test_qa15b_steps_spread_over_distinct_step_indexes_keep_operation_order(api):  # noqa: F811
    api.world = World(_rows(("A", "aa", 1), ("B", "bbb", 2), ("C", "c", 3)))
    data = api.get().json()
    assert [(s["step_index"], s["locator_name"], s["text_chars"]) for s in data["type_steps"]] == [
        (1, "A", 2), (2, "B", 3), (3, "C", 1)]


def test_qa15b_long_unicode_locator_name_is_returned_whole_and_json_clean(api):  # noqa: F811
    name = "Trường nhập “tên” đăng nhập Ư"  # the locator value is bounded by the contract
    api.world = World(_rows((name, "abc", 1)))
    response = api.get()
    assert response.status_code == 200
    assert response.json()["type_steps"][0]["locator_name"].startswith("Trường nhập")
    assert response.json()["type_steps"][0]["text_chars"] == 3


def test_qa15b_flag_off_with_type_steps_never_leaks_a_length_or_name(api):  # noqa: F811
    api.world = World(_rows(("Ô nhập số", "x" * 17, 1)), owned=False)
    response = api.get()
    assert response.json() == {"owned_test_target": False, "has_type_steps": True, "type_steps": []}
    assert "Ô nhập số" not in response.text and "17" not in response.text


def test_qa15b_response_headers_on_success_and_404_do_not_cache_the_value_response(api):  # noqa: F811
    assert api.get().headers["cache-control"] == "private, no-store"
