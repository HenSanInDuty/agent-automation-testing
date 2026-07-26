"""Vendor-neutral trace context and metric export boundary.

The W3C traceparent-compatible identifiers can be exported by an OpenTelemetry
SDK without changing application/workflow/worker contracts.
"""

from collections import Counter
from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class TraceContext:
    correlation_id: UUID
    trace_id: str
    span_id: str

    def traceparent(self) -> str:
        return f"00-{self.trace_id}-{self.span_id}-01"


_context: ContextVar[TraceContext | None] = ContextVar("trace_context", default=None)


def trace_context(correlation_id: UUID, parent_traceparent: str | None = None) -> TraceContext:
    """Start a child span, retaining a valid upstream W3C trace identifier."""
    trace_id = uuid4().hex
    if parent_traceparent:
        parts = parent_traceparent.split("-")
        if len(parts) == 4 and len(parts[1]) == 32 and len(parts[2]) == 16:
            try:
                int(parts[1], 16)
                int(parts[2], 16)
                trace_id = parts[1]
            except ValueError:
                pass
    context = TraceContext(correlation_id, trace_id, uuid4().hex[:16])
    _context.set(context)
    return context


def current_trace_context() -> TraceContext | None:
    return _context.get()


class Metrics:
    """Small exporter port used by local tests; production plugs in an OTEL exporter."""

    metric_names = (
        "queue_delay",
        "run_duration",
        "retry_count",
        "failure_class",
        "artifact_failure",
        "agent_latency",
        "agent_cost",
        "proposal_acceptance",
        "false_healing",
    )

    def __init__(self) -> None:
        self.counters: Counter[str] = Counter()
        for name in self.metric_names:
            self.counters[name] = 0

    def increment(self, name: str) -> None:
        self.counters[name] += 1

    def snapshot(self) -> dict[str, int]:
        return dict(self.counters)

    def prometheus(self) -> str:
        """Render a dependency-free scrape format for the self-hosted default."""
        return (
            "\n".join(
                f"auto_at_{name}_total {value}" for name, value in sorted(self.counters.items())
            )
            + "\n"
        )


metrics = Metrics()
