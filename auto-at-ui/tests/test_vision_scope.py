import pytest
from domain.vision_scope import interaction_scope


@pytest.mark.parametrize("intent", [
    "Kiểm tra tình trạng hoạt  động của toàn bộ nút trong trang web",
    "Kiểm tra các nút", "Test all buttons on the page.",
    "Kiểm tra các nút xem có hoạt động không",
    "Kiểm tra các nút có hoạt động không?",
    "Kiểm tra tất cả nút bấm trên website xem có hoạt động hay không?",
])
def test_explicit_button_scope(intent):
    assert interaction_scope(intent) == "visual_buttons"


@pytest.mark.parametrize("intent", [
    "Kiểm tra nút và liên kết", "Do not test all buttons", "Explore the site",
    "Check all buttons and links", "Click the link named nút", "Check the Save button",
    "Kiểm tra các nút và liên kết xem có hoạt động không",
    "Không kiểm tra các nút xem có hoạt động không",
    "Kiểm tra các nút xem có hoạt động không rồi đăng nhập",
])
def test_ambiguous_mixed_or_named_tasks_are_not_narrowed_by_a_keyword(intent):
    assert interaction_scope(intent) == "all"
