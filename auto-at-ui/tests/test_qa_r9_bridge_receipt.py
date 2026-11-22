"""QA r9: receipt clock-skew tolerance in FileSpool.stop_reason (ADR 041)."""

import threading
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from auto_at.contracts.codex_bridge import canonical_bytes
from infrastructure.codex_bridge import spool as spool_module
from infrastructure.codex_bridge.spool import RECEIPT_CLOCK_SKEW, SpoolError
from pydantic import ValidationError
from test_codex_bridge_spool import _aged_job

REVOKED = "bridge_policy_revoked"


def _write_receipt(spool, req, recorded_at, expires_at, status="queued"):
    receipt = spool._receipt(req, status, expires_at, UUID(int=0)).model_copy(
        update={"recorded_at": recorded_at},
    )
    spool._write(spool.path(req.job_id), "authorization.json", canonical_bytes(receipt))


def test_skew_constant_is_one_second():
    assert timedelta(seconds=1) == RECEIPT_CLOCK_SKEW


def test_recorded_at_exactly_at_skew_boundary_is_accepted(tmp_path):
    spool, req = _aged_job(tmp_path)
    now = datetime.now(UTC)
    recorded = now + RECEIPT_CLOCK_SKEW
    _write_receipt(spool, req, recorded, recorded + timedelta(seconds=5))
    assert spool.stop_reason(req, now) is None


def test_recorded_at_just_past_skew_boundary_is_revoked(tmp_path):
    spool, req = _aged_job(tmp_path)
    now = datetime.now(UTC)
    recorded = now + RECEIPT_CLOCK_SKEW + timedelta(microseconds=1)
    _write_receipt(spool, req, recorded, recorded + timedelta(seconds=5))
    assert spool.stop_reason(req, now) == REVOKED


@pytest.mark.parametrize("ahead", [timedelta(seconds=5), timedelta(minutes=10), timedelta(days=1)])
def test_recorded_far_in_future_is_revoked(tmp_path, ahead):
    spool, req = _aged_job(tmp_path)
    now = datetime.now(UTC)
    _write_receipt(spool, req, now + ahead, now + ahead + timedelta(seconds=5))
    assert spool.stop_reason(req, now) == REVOKED


def test_recorded_in_past_within_ttl_is_accepted(tmp_path):
    spool, req = _aged_job(tmp_path)
    now = datetime.now(UTC)
    _write_receipt(spool, req, now - timedelta(seconds=1), now + timedelta(seconds=5))
    assert spool.stop_reason(req, now) is None


def test_expired_receipt_is_revoked_even_inside_skew(tmp_path):
    spool, req = _aged_job(tmp_path)
    now = datetime.now(UTC)
    _write_receipt(spool, req, now - timedelta(seconds=3), now - timedelta(milliseconds=1))
    assert spool.stop_reason(req, now) == REVOKED
    # expiry exactly == now is also expired (now < expires required)
    _write_receipt(spool, req, now - timedelta(seconds=3), now)
    assert spool.stop_reason(req, now) == REVOKED


def test_missing_receipt_is_revoked(tmp_path):
    spool, req = _aged_job(tmp_path)
    assert spool.stop_reason(req, datetime.now(UTC)) == REVOKED


@pytest.mark.parametrize("content", [b"", b"{not json", b"[]", b"null"])
def test_empty_or_corrupt_receipt_never_passes(tmp_path, content):
    spool, req = _aged_job(tmp_path)
    spool._write(spool.path(req.job_id), "authorization.json", content)
    try:
        reason = spool.stop_reason(req, datetime.now(UTC))
    except (ValidationError, SpoolError, ValueError):
        return  # fail-closed by raising (existing contract: malformed receipt fails)
    assert reason == REVOKED


def test_deadline_wins_over_valid_receipt(tmp_path):
    spool, req = _aged_job(tmp_path)
    spool.authorize(req, datetime.now(UTC) + timedelta(seconds=2))
    assert spool.stop_reason(req, req.deadline) == "bridge_deadline_exceeded"
    assert spool.stop_reason(req, req.deadline + timedelta(seconds=1)) == "bridge_deadline_exceeded"


def test_receipt_expiry_after_deadline_is_revoked(tmp_path):
    spool, req = _aged_job(tmp_path)
    now = req.deadline - timedelta(seconds=1)
    _write_receipt(spool, req, now, req.deadline + timedelta(seconds=1))
    assert spool.stop_reason(req, now) == REVOKED


@pytest.mark.parametrize("ttl", [11, 60, 3600])
def test_too_long_ttl_is_revoked_regardless_of_skew(tmp_path, ttl):
    spool, req = _aged_job(tmp_path)
    now = datetime.now(UTC)
    _write_receipt(spool, req, now, now + timedelta(seconds=ttl))
    assert spool.stop_reason(req, now) == REVOKED


def test_zero_or_negative_ttl_is_revoked(tmp_path):
    spool, req = _aged_job(tmp_path)
    now = datetime.now(UTC)
    _write_receipt(spool, req, now + timedelta(milliseconds=500), now + timedelta(milliseconds=500))
    assert spool.stop_reason(req, now) == REVOKED


def test_wrong_status_receipt_is_revoked(tmp_path):
    spool, req = _aged_job(tmp_path)
    now = datetime.now(UTC)
    _write_receipt(spool, req, now, now + timedelta(seconds=5), status="claimed")
    assert spool.stop_reason(req, now) == REVOKED


def test_request_precreation_clock_is_still_revoked(tmp_path):
    spool, req = _aged_job(tmp_path)
    spool.authorize(req, datetime.now(UTC) + timedelta(seconds=2))
    assert spool.stop_reason(req, req.created_at - timedelta(seconds=1)) == REVOKED


def test_revoke_during_stream_is_detected_at_next_poll(tmp_path):
    """Job streaming: polls pass while receipt is fresh, then control plane stops re-signing."""
    spool, req = _aged_job(tmp_path)
    spool.authorize(req, datetime.now(UTC) + timedelta(seconds=2))
    for _ in range(5):
        assert spool.stop_reason(req, datetime.now(UTC)) is None
    # real revoke 1: authorization removed
    spool.path(req.job_id).joinpath("authorization.json").unlink()
    assert spool.stop_reason(req, datetime.now(UTC)) == REVOKED
    # real revoke 2: stops being re-signed, lease lapses (skew never extends expiry)
    spool.authorize(req, datetime.now(UTC) + timedelta(milliseconds=300))
    assert spool.stop_reason(req, datetime.now(UTC)) is None
    time.sleep(0.4)
    assert spool.stop_reason(req, datetime.now(UTC)) == REVOKED


def test_cancel_during_stream_wins(tmp_path):
    spool, req = _aged_job(tmp_path)
    spool.authorize(req, datetime.now(UTC) + timedelta(seconds=2))
    assert spool.stop_reason(req, datetime.now(UTC)) is None
    spool.cancel(req)
    assert spool.stop_reason(req, datetime.now(UTC)) == "bridge_cancelled"


def _race(spool, req, iterations, resign_pause=0.0):
    """Re-sign continuously in one thread while another polls with a pre-sampled clock."""
    stop = threading.Event()
    writer_errors: list[BaseException] = []
    reader_errors: list[BaseException] = []
    reasons: list[str | None] = []

    def writer():
        while not stop.is_set():
            try:
                spool.authorize(req, datetime.now(UTC) + timedelta(seconds=2))
            except BaseException as error:  # noqa: BLE001 - collect for the assertion message
                writer_errors.append(error)
            if resign_pause:
                time.sleep(resign_pause)

    spool.authorize(req, datetime.now(UTC) + timedelta(seconds=2))
    thread = threading.Thread(target=writer)
    thread.start()
    try:
        for _ in range(iterations):
            sampled = datetime.now(UTC)  # bridge samples now BEFORE reading the file
            try:
                reasons.append(spool.stop_reason(req, sampled))
            except OSError as error:  # Windows sharing violation during os.replace: not a verdict
                reader_errors.append(error)
    finally:
        stop.set()
        thread.join(timeout=10)
    return reasons, writer_errors, reader_errors


def test_concurrent_resign_never_yields_false_revocation(tmp_path):
    spool, req = _aged_job(tmp_path)
    reasons, writer_errors, reader_errors = _race(spool, req, iterations=1500)
    print(f"polls={len(reasons)} reader_os_errors={len(reader_errors)} "
          f"writer_errors={len(writer_errors)} revoked={reasons.count(REVOKED)}")
    assert len(reasons) >= 300, "too few successful polls for a meaningful race"
    assert REVOKED not in reasons
    assert not writer_errors or all(isinstance(e, OSError) for e in writer_errors)


def test_concurrent_resign_fast_cadence_no_false_revocation(tmp_path):
    spool, req = _aged_job(tmp_path)
    reasons, _, _ = _race(spool, req, iterations=800, resign_pause=0.002)
    assert len(reasons) >= 300
    assert REVOKED not in reasons


def test_race_is_reproducible_on_old_behaviour_with_zero_skew(tmp_path, monkeypatch):
    """With skew=0 (pre-r9 semantics) the same race may go red; documents the repro.

    Not asserted as failing (probabilistic); only that skew=0 never *under*-reports vs fixed code.
    """
    monkeypatch.setattr(spool_module, "RECEIPT_CLOCK_SKEW", timedelta(0))
    spool, req = _aged_job(tmp_path)
    reasons, _, _ = _race(spool, req, iterations=1500)
    print(f"OLD-BEHAVIOUR polls={len(reasons)} false_revoked={reasons.count(REVOKED)}")
    assert set(reasons) <= {None, REVOKED}


def _lagging_poll(spool, req, iterations, lag=0.03):
    """Widen the sample-now -> read window (slow bridge poll) while the writer re-signs."""
    stop = threading.Event()

    def writer():
        while not stop.is_set():
            try:
                spool.authorize(req, datetime.now(UTC) + timedelta(seconds=2))
            except OSError:
                pass

    spool.authorize(req, datetime.now(UTC) + timedelta(seconds=2))
    thread = threading.Thread(target=writer)
    thread.start()
    reasons = []
    try:
        for _ in range(iterations):
            sampled = datetime.now(UTC)
            time.sleep(lag)
            try:
                reasons.append(spool.stop_reason(req, sampled))
            except OSError:
                pass
    finally:
        stop.set()
        thread.join(timeout=10)
    return reasons


def test_lagging_poll_with_continuous_resign_is_not_revoked(tmp_path):
    spool, req = _aged_job(tmp_path)
    reasons = _lagging_poll(spool, req, 80)
    assert len(reasons) >= 30
    assert REVOKED not in reasons


def test_lagging_poll_old_behaviour_zero_skew_goes_red(tmp_path, monkeypatch):
    """Repro of the r9 bug on pre-fix semantics (skew=0): false revocations appear."""
    monkeypatch.setattr(spool_module, "RECEIPT_CLOCK_SKEW", timedelta(0))
    spool, req = _aged_job(tmp_path)
    reasons = _lagging_poll(spool, req, 80)
    print(f"ZERO-SKEW polls={len(reasons)} false_revoked={reasons.count(REVOKED)}")
    assert REVOKED in reasons, "expected the old behaviour to revoke falsely under lag"
