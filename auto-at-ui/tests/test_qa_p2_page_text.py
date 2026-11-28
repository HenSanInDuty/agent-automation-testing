# ruff: noqa: E501
"""QA phase 02 (ADR-046 `page-text-v1`): contract side, plus worker output captured by `qa-page-text.spec.ts`.

The two worker-output tests read JSON the Playwright QA spec writes into the temp dir; they skip when it is absent.
"""

import json
import tempfile
from pathlib import Path

import pytest
from auto_at.contracts.codex_bridge import (
    CodexDomObservation,
    CodexPageTextItem,
    canonical_bytes,
    content_hash,
)
from pydantic import ValidationError

FIXTURES = Path(__file__).resolve().parents[1] / "packages/contracts/fixtures/vision-worker-v4"
TMP = Path(tempfile.gettempdir())
NEW = ("page_text", "page_text_truncated", "page_text_skipped")


def base(**extra):
    return {
        "tenant_id": "t", "project_id": "00000000-0000-0000-0000-000000000001",
        "session_id": "00000000-0000-0000-0000-000000000002", "fencing_token": 1,
        "observation_id": "00000000-0000-0000-0000-000000000004",
        "snapshot_id": "00000000-0000-0000-0000-000000000003", "state_fingerprint": "a" * 64,
        "captured_at": "2026-11-26T09:00:00Z", "viewport": {"width": 1280, "height": 720},
        "elements": [], "truncated": False, "scrollable": False, "skipped_count": 0, **extra,
    }


def item(text, kind="paragraph"):
    return {"kind": kind, "text": text}


def test_qa_c01_old_fixtures_do_not_mention_page_text_and_still_validate():
    old = [p for p in FIXTURES.glob("*.json") if "page-text" not in p.name]
    assert old and not [p.name for p in old if "page_text" in p.read_text(encoding="utf-8")]
    # the one observation-shaped fixture family: elements-only observation keeps its exact canonical form
    plain = CodexDomObservation.model_validate(base())
    assert json.loads(canonical_bytes(plain)).keys() == set(base().keys()) | {"schema_version", "unsupported"}


def test_qa_c02_page_text_keys_appear_only_when_non_default():
    for extra, keys in (({}, set()), ({"page_text_truncated": True}, {"page_text_truncated"}),
                        ({"page_text_skipped": 2}, {"page_text_skipped"}),
                        ({"page_text": [item("Xin chào")]}, {"page_text"})):
        dumped = CodexDomObservation.model_validate(base(**extra)).model_dump(mode="json")
        assert {k for k in NEW if k in dumped} == keys


def test_qa_c03_hash_unchanged_by_explicit_defaults():
    plain = CodexDomObservation.model_validate(base())
    explicit = CodexDomObservation.model_validate(base(page_text=[], page_text_truncated=False, page_text_skipped=0))
    assert canonical_bytes(plain) == canonical_bytes(explicit) and content_hash(plain) == content_hash(explicit)
    with_text = CodexDomObservation.model_validate(base(page_text=[item("x")]))
    assert content_hash(with_text) != content_hash(plain)


@pytest.mark.parametrize("text", [
    "Liên hệ nguoi@example.com", "password=abc", "Reset password", "my token here", "Mã 12345678",
    "https://x.test/a", "[redacted]", "API KEY", "Authorization", "cookie", " leading", "trailing ", "tab\there", "line\nbreak",
])
def test_qa_c04_python_rejects_sensitive_or_unclean_page_text(text):
    with pytest.raises(ValidationError):
        CodexDomObservation.model_validate(base(page_text=[item(text)]))
    with pytest.raises(ValidationError):
        CodexPageTextItem(kind="heading", text=text)


def test_qa_c05_python_limits_items_chars_bytes_and_kind():
    CodexDomObservation.model_validate(base(page_text=[item(f"m{i}") for i in range(24)]))
    with pytest.raises(ValidationError):
        CodexDomObservation.model_validate(base(page_text=[item(f"m{i}") for i in range(25)]))
    CodexPageTextItem(kind="alert", text="x" * 160)
    with pytest.raises(ValidationError):
        CodexPageTextItem(kind="alert", text="x" * 161)
    with pytest.raises(ValidationError):
        CodexPageTextItem(kind="alert", text="")
    with pytest.raises(ValidationError):
        CodexPageTextItem(kind="link", text="x")
    with pytest.raises(ValidationError):
        CodexPageTextItem.model_validate({"kind": "alert", "text": "x", "extra": 1})
    nine = [item("ế" * 150) for _ in range(9)]  # 450 bytes each -> 4050
    CodexDomObservation.model_validate(base(page_text=nine))
    with pytest.raises(ValidationError):
        CodexDomObservation.model_validate(base(page_text=[item(f"{i:02d}" + "ế" * 150) for i in range(10)]))
    with pytest.raises(ValidationError):
        CodexDomObservation.model_validate(base(page_text_skipped=-1))


def test_qa_c06_unicode_items_roundtrip():
    texts = ["😀 Xin chào ✓ 世界", "مرحبا بالعالم", "Tiếng Việt có dấu: ắằẳẵặ"]
    obs = CodexDomObservation.model_validate(base(page_text=[item(t) for t in texts]))
    again = CodexDomObservation.model_validate_json(canonical_bytes(obs))
    assert [i.text for i in again.page_text] == texts


def test_qa_c07_accepted_page_text_fixture_parses_and_old_fixtures_untouched():
    new = json.loads((FIXTURES / "dom-observation.page-text.accepted.json").read_text(encoding="utf-8"))
    obs = CodexDomObservation.model_validate(new["payload"]["data"]["observation"])
    assert obs.page_text_truncated and obs.page_text_skipped == 2 and len(obs.page_text) == 3


# Round 2: C08 expected Python to ACCEPT worker-bypassing strings. That direction was wrong (the phase forbids loosening
# the Python filter). Invariant now: Python still rejects them; the worker (C09, C11) must be the side that drops them.
@pytest.mark.parametrize("text", ["Mã ١٢٣٤٥٦٧٨ ở đây", "đ@example.com"])
def test_qa_c08_python_filter_still_rejects_unicode_sensitive_text(text):
    with pytest.raises(ValidationError):
        CodexPageTextItem(kind="paragraph", text=text)


def test_qa_c09_worker_output_of_those_strings_parses_in_python():
    path = TMP / "qa-p2-digits-observation.json"
    if not path.exists():
        pytest.skip("run qa-page-text.spec.ts first")
    CodexDomObservation.model_validate(json.loads(path.read_text(encoding="utf-8")))


def test_qa_c10_real_worker_output_without_capability_hashes_like_the_old_shape():
    path = TMP / "qa-p2-plain-observation.json"
    if not path.exists():
        pytest.skip("run qa-page-text.spec.ts first")
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert all(key in raw for key in NEW)  # the TS wire carries the defaults ...
    stripped = {k: v for k, v in raw.items() if k not in NEW}
    new_side = CodexDomObservation.model_validate(raw)
    old_side = CodexDomObservation.model_validate(stripped)  # ... the old shape has none
    assert canonical_bytes(new_side) == canonical_bytes(old_side)
    assert content_hash(new_side) == content_hash(old_side)
    assert not any(key in json.loads(canonical_bytes(new_side)) for key in NEW)


# ---- Round 2 attack: find a string the worker KEEPS but Python REJECTS (would lose the whole observation) ----
CAND = TMP / "qa-p2-candidates.json"
KEPT = TMP / "qa-p2-kept.json"
BATCH = 16


def python_rejects(text):
    try:
        CodexPageTextItem(kind="paragraph", text=text)
    except ValidationError:
        return True
    return False


def build_candidates():
    import unicodedata
    words = ["password", "passwd", "secret", "token", "api key", "api_key", "authorization", "cookie"]
    zw = ["​", "‌", "‍", "﻿", "­", "⁠"]
    out = []
    for w in words:
        forms = {w, w.upper(), w.title(), unicodedata.normalize("NFD", w) + "́", w[:2] + "́" + w[2:],
                 w.replace("k", "K"), w.replace("s", "ſ"), w.replace("i", "ı"), w.replace("i", "İ"),
                 w.replace("o", "ö"), w.replace("t", "ｔ")}
        forms |= {w[:3] + z + w[3:] for z in zw}
        for f in forms:
            for ctx in ("{}", "x {} y", "{}_x", "x_{}", "‿{}", "{}‿", "²{}", "{}²", "Ⅷ{}", "{}Ⅷ",
                        "ª{}", "{}́", "́{}", "ǅ{}", "{}ʰ", "{}ᴬ", "{}٣", "1{}"):
                out.append(ctx.format(f))
    for local in ("a", "đ", "á", "ü", "x​", "٣", "Ⅷ", "a‿", "ａ", "aı"):
        for at in ("@", "＠", "﹫", "@​"):
            for dom in ("b.com", "b．com", "b.ſo", "b.KK", "đ.vn", "b.CO", "b.çö", "b。com", "b́.com"):
                out.append(f"{local}{at}{dom}")
    zeros = sorted({c for c in map(chr, range(0x110000)) if unicodedata.category(c) == "Nd" and unicodedata.digit(c) == 0})
    for z in zeros:
        run = "".join(chr(ord(z) + i) for i in range(1, 8)) if unicodedata.category(chr(ord(z) + 7)) == "Nd" else z * 7
        for ctx in ("{}", "x {} y", "x{}", "{}x", "{}́", "́{}", "{}_", "_{}", "{}²", "1234{}"):
            out.append(ctx.format(run))
        out.append("1234" + run[:3])
        out.append(run[:4] + "567")
    out += ["[REDACTED]", "[Redacted]", "hTTps://x", "HTTP://x", "https∶//x", "http://​x", "ｈttp://x",
            "a_" + "٣" * 7, "٣" * 7 + "ʰ", "٣" * 6 + "1", "١٢٣٤٥٦٧", "١٢٣-٤٥٦٧"]
    extra = ["maİl@example.com", "mail@exİmple.com", "https://exİmple.com", "httpİ://x", "maıl@example.com",
             "apİ​key", "apİ​ key", "coo​kİe", "cook​ıe", "api̇ key", "İ",
             "apİ key", "cookİe", "cooki̇e", "apｉ key", "cookＩe", "authorｉzation",
             "apİ key", "APİ KEY", "APı KEY", "passİwd", "tokeın", "secrİt", "tokİn", "cookİıe",
             "authorizatıon", "AUTHORİZATİON", "İİİ token", "tokenİ", "ıtoken"]
    out += extra
    for w in ("api key", "cookie", "authorization"):
        for z in zw + ["̇", "́", "_"]:
            for i_ in ("İ", "ı", "İ", "ｉ", "Ｉ"):
                out.append(w.replace("i", i_, 1).replace("i", i_ + z, 1) if "i" in w else w)
                out.append(w.replace("i", z + i_))
                out.append(w.replace("i", i_ + z))
    uniq = list(dict.fromkeys(t for t in out if t == t.strip() and len(t) <= 150))
    return [t for t in uniq if python_rejects(t)]


def test_qa_c11a_write_candidates():
    cand = build_candidates()
    assert cand
    CAND.write_text(json.dumps(cand, ensure_ascii=False), encoding="utf-8")
    print(f"candidates (all rejected by Python): {len(cand)}")


def test_qa_c11b_nothing_python_rejects_survives_the_worker():
    if not KEPT.exists():
        pytest.skip("run qa-page-text.spec.ts (QA-W10) first")
    data = json.loads(KEPT.read_text(encoding="utf-8"))
    survivors = [t for t in data["kept"] if python_rejects(t)]
    assert data["sent"] > 0 and data["kept_total"] == len(data["kept"])
    assert survivors == [], f"worker kept {len(survivors)} of {data['sent']} Python-rejected strings: {survivors[:10]!r}"


def test_qa_c12_lone_surrogate_page_text_from_worker_is_handled_by_python():
    path = TMP / "qa-p2-surrogate-observation.json"
    if not path.exists():
        pytest.skip("run qa-page-text.spec.ts (QA-W11) first")
    obs = CodexDomObservation.model_validate(json.loads(path.read_text(encoding="utf-8")))
    canonical_bytes(obs)  # must not raise on encode
    content_hash(obs)
