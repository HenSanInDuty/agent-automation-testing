import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_observability_stack_keeps_correlation_fields_out_of_loki_labels() -> None:
    fluent = (ROOT / "observability/fluent-bit/fluent-bit.conf").read_text()
    dashboard = json.loads(
        (ROOT / "observability/grafana/dashboards/run-investigation.json").read_text()
    )
    compose = (ROOT / "docker-compose.yml").read_text()

    assert "Labels        service=$service,environment=$environment,level=$level" in fluent
    assert "correlation_id" not in fluent.split("Labels", 1)[1].split("\n", 1)[0]
    assert "Only first-party JSON envelopes proceed to Loki" in (
        ROOT / "observability/fluent-bit/redact.lua"
    ).read_text()
    assert "| json | correlation_id" in dashboard["panels"][0]["targets"][0]["expr"]
    assert "fluent-bit:" in compose and "loki:" in compose and "grafana:" in compose
