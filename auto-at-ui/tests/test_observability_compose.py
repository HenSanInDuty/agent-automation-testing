import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_observability_stack_keeps_correlation_fields_out_of_loki_labels() -> None:
    fluent = (ROOT / "observability/fluent-bit/fluent-bit.conf").read_text()
    dashboard = json.loads(
        (ROOT / "observability/grafana/dashboards/run-investigation.json").read_text()
    )
    grafana_dockerfile = (ROOT / "observability/grafana/Dockerfile").read_text()
    dashboard_provisioning = (
        ROOT / "observability/grafana/provisioning/dashboards/dashboard.yaml"
    ).read_text()
    compose = (ROOT / "docker-compose.yml").read_text()

    assert "Labels        service=$service,environment=$environment,level=$level" in fluent
    assert "Read_from_Head    On" in fluent
    assert "Refresh_Interval  5" in fluent
    assert "DB                /buffers/tail.db" in fluent
    assert "correlation_id" not in fluent.split("Labels", 1)[1].split("\n", 1)[0]
    assert "Only first-party JSON envelopes proceed to Loki" in (
        ROOT / "observability/fluent-bit/redact.lua"
    ).read_text()
    assert ' |= "$search_id"' in dashboard["panels"][0]["targets"][0]["expr"]
    assert dashboard["templating"]["list"][0]["name"] == "search_id"
    assert dashboard["panels"][0]["options"]["showTime"] is True
    failures = next(panel for panel in dashboard["panels"] if panel["id"] == 2)
    expression = failures["targets"][0]["expr"]
    assert 'stage!="operation_ack"' in expression
    assert 'stage!="operation_read"' in expression
    assert 'line_format' in expression
    assert 'OPERATION {{.operation_status}}' in expression
    assert 'reason={{.outcome_code}}' in expression
    assert failures["gridPos"]["y"] == 0
    assert "fluent-bit:" in compose and "loki:" in compose and "grafana:" in compose
    assert "build: ./observability/loki" in compose
    assert "build: ./observability/fluent-bit" in compose
    assert "build: ./observability/grafana" in compose
    assert "COPY dashboards /etc/grafana/dashboards" in grafana_dockerfile
    assert "path: /etc/grafana/dashboards" in dashboard_provisioning
    assert "until nc -z rustfs 9000" in compose
