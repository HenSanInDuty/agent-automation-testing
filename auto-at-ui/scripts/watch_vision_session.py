"""Poll an existing Vision session with bounded output and no execution side effects."""

import argparse
import json
import math
import sys
import time
from pathlib import Path
from uuid import UUID

import httpx

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "packages" / "contracts" / "src"))

from auto_at.contracts.vision import VisualExplorationState  # noqa: E402

TERMINAL = {"completed", "cancelled", "unavailable"}


def emit_json(record):
    print(json.dumps(record), flush=True)


def watch(client, session_id, *, interval=30, timeout=1800, changes=False,
          emit=emit_json, clock=time.monotonic, sleep=time.sleep):
    """Return 0 for terminal observation, 1 for errors, 2 for monitor timeout.

    Terminal observation is not a passing benchmark verdict. A monitor timeout
    never cancels the underlying exploration. No POST or automatic retry is made.
    """
    session_id = str(UUID(str(session_id)))
    if not all(math.isfinite(v) and v > 0 for v in (interval, timeout)):
        raise ValueError("interval and timeout must be finite and positive")
    deadline = clock() + timeout
    previous = None
    while True:
        remaining = deadline - clock()
        if remaining <= 0:
            emit({"event": "monitor_timeout", "session_id": session_id, "state": previous})
            return 2
        try:
            response = client.get(f"/api/v1/vision/explorations/{session_id}",
                                  timeout=min(30, remaining))
            response.raise_for_status()
            data = response.json()
            if str(UUID(data["id"])) != session_id:
                raise ValueError("session scope mismatch")
            state = VisualExplorationState(data["state"]).value
        except httpx.HTTPError as error:
            status = (error.response.status_code
                      if isinstance(error, httpx.HTTPStatusError) else None)
            emit({"event": "http_failure", "session_id": session_id, "status": status})
            return 1
        except (ValueError, KeyError, TypeError, AttributeError):
            emit({"event": "invalid_response", "session_id": session_id})
            return 1
        if state in TERMINAL:
            emit({"event": "terminal", "session_id": session_id, "state": state})
            return 0
        if changes and state != previous:
            emit({"event": "state_changed", "session_id": session_id, "state": state})
        previous = state
        sleep(min(interval, max(0, deadline - clock())))


def positive_seconds(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be finite and positive")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=UUID, required=True)
    parser.add_argument("--api", default="http://127.0.0.1:7000")
    parser.add_argument("--headers-file", type=Path, required=True,
                        help="Private JSON auth headers; never printed")
    parser.add_argument("--interval", type=positive_seconds, default=30)
    parser.add_argument("--timeout", type=positive_seconds, default=1800)
    parser.add_argument("--changes", action="store_true", help="Also emit state transitions")
    args = parser.parse_args()
    try:
        headers = json.loads(args.headers_file.read_text(encoding="utf-8"))
        if not isinstance(headers, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in headers.items()
        ):
            raise ValueError("invalid headers")
        with httpx.Client(base_url=args.api, headers=headers, follow_redirects=False) as client:
            return watch(client, args.session, interval=args.interval,
                         timeout=args.timeout, changes=args.changes)
    except (OSError, ValueError, TypeError):
        emit_json({"event": "invalid_configuration"})
        return 1
    except KeyboardInterrupt:
        emit_json({"event": "monitor_interrupted"})
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
