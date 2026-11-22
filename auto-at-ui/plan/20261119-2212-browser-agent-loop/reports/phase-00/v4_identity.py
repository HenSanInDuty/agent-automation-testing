# ruff: noqa: E501
"""Tính hash đối chứng v4 (phase 0): schema CodexOutput và prompt+schema codex-dom-v11.

Chạy từ gốc repo, không ghi file:
    uv run python -I plan/20261119-2212-browser-agent-loop/reports/phase-00/v4_identity.py

Mọi giá trị đầu vào là cố định (UUID, thời điểm, observation, task) để kết quả
tái lập được giữa các lần chạy. Request mẫu bám theo helper `observation()`/`request()`
trong tests/test_codex_bridge_contracts.py và `task_context()` trong
apps/control-plane/agents/vision/codex_service.py, nhưng thay UUID/NOW bằng hằng số.
"""

import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / "apps" / "control-plane"), str(ROOT / "packages" / "contracts" / "src")]

from agents.prompts.codex_exploration import (  # noqa: E402
    PROMPT_VERSION,
    build_prompt,
    with_response_schema,
)
from agents.vision.codex_service import output_schema, task_context  # noqa: E402
from auto_at.contracts.codex_bridge import (  # noqa: E402
    CodexBridgeRequest,
    CodexConsentSnapshot,
    CodexDomObservation,
    CodexOutput,
    canonical_bytes,
    content_hash,
)
from pydantic import TypeAdapter  # noqa: E402

NOW = datetime(2026, 10, 23, 12, tzinfo=UTC)
CANDIDATE_LIMIT = 3
TASK_INTENT = "Check buttons on the fixture page"


def u(n: int) -> UUID:
    return UUID(int=n)


def sample_observation() -> CodexDomObservation:
    return CodexDomObservation.model_validate({
        "tenant_id": "fixture", "project_id": u(1), "session_id": u(2), "fencing_token": 1,
        "observation_id": u(3), "snapshot_id": u(4), "state_fingerprint": "a" * 64,
        "captured_at": NOW, "viewport": {"width": 1280, "height": 720},
        "elements": [{
            "element_id": "e_" + "a" * 32, "role": "button", "name": "Continue",
            "enabled": True, "editable": False,
        }],
    })


def sample_request(obs: CodexDomObservation) -> CodexBridgeRequest:
    consent = CodexConsentSnapshot(dom_transfer_accepted=True, dom_transfer_provider="codex_cli")
    return CodexBridgeRequest.model_validate({
        **{key: getattr(obs, key) for key in (
            "tenant_id", "project_id", "session_id", "fencing_token", "observation_id",
            "snapshot_id", "state_fingerprint",
        )},
        "job_id": u(5), "bridge_id": u(6), "correlation_id": u(7), "request_sequence": 1,
        "prompt_version": PROMPT_VERSION, "stage": "dom", "created_at": NOW,
        "deadline": NOW + timedelta(seconds=120), "consent": consent,
        "consent_hash": content_hash(consent), "candidate_limit": CANDIDATE_LIMIT,
        "context": task_context(TASK_INTENT),
        "inputs": {
            "dom_sha256": content_hash(obs), "dom_bytes": len(canonical_bytes(obs)),
            "schema_sha256": "b" * 64, "schema_bytes": 100,
        },
    })


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    # Hash 1: schema CodexOutput (canonical JSON, sort_keys, separators compact, ASCII).
    schema_dict = TypeAdapter(CodexOutput).json_schema()
    schema_canonical = json.dumps(schema_dict, sort_keys=True, separators=(",", ":")).encode()

    # Hash 2: prompt codex-dom-v11 + schema bridge (output_schema(CANDIDATE_LIMIT)) cho request mẫu.
    obs = sample_observation()
    req = sample_request(obs)
    prompt = build_prompt(req, canonical_bytes(obs))
    bridge_schema = output_schema(CANDIDATE_LIMIT)
    wrapped = with_response_schema(prompt, bridge_schema)

    result = {
        "prompt_version": PROMPT_VERSION,
        "codex_output_schema": {
            "sha256": sha256(schema_canonical),
            "bytes": len(schema_canonical),
            "source": "TypeAdapter(CodexOutput).json_schema() from packages/contracts/src/auto_at/contracts/codex_bridge.py (CodexOutput)",
            "canonical": "json.dumps(schema, sort_keys=True, separators=(',',':')).encode() (ensure_ascii default)",
        },
        "codex_dom_v11_prompt_plus_schema": {
            "sha256": sha256(wrapped),
            "bytes": len(wrapped),
            "prompt_sha256": sha256(prompt),
            "bridge_schema_sha256": sha256(bridge_schema),
            "candidate_limit": CANDIDATE_LIMIT,
            "stage": "dom",
            "source": "apps/control-plane/agents/vision/codex_service.py output_schema(3) + apps/control-plane/agents/prompts/codex_exploration.py build_prompt/with_response_schema; request mẫu = sample_request() trong script, dựa trên tests/test_codex_bridge_contracts.py observation()/request() và tests/test_codex_candidate_service.py (task_context, prompt test) với UUID/NOW cố định",
            "computation": "sha256(with_response_schema(build_prompt(req, canonical_bytes(obs)), output_schema(3)))",
        },
    }
    print(json.dumps(result, indent=2, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
