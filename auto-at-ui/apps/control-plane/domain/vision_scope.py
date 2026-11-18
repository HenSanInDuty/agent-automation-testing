"""Conservative recognition of explicit all-buttons requests, never page text."""

import re
import unicodedata


def interaction_scope(intent: str) -> str:
    text = " ".join(unicodedata.normalize("NFC", intent).casefold().split()).strip(".!? ")
    patterns = (
        r"(?:kiểm tra|test)(?: tình trạng)?(?: hoạt động)?(?: của)? "
        r"(?:toàn bộ|tất cả|các) nút(?: bấm)?"
        r"(?: (?:trong|trên) (?:trang web|website|trang|web))?"
        r"(?: (?:xem )?có hoạt động (?:không|hay không))?",
        r"(?:test|check|verify) (?:all|the) buttons"
        r"(?: (?:on|in) (?:the )?(?:page|website|site))?",
    )
    return "visual_buttons" if any(re.fullmatch(pattern, text) for pattern in patterns) else "all"
