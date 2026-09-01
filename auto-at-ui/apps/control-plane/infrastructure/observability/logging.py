"""Safe JSON logging primitives for first-party runtime services."""

import json
import logging
import re
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from config import Settings

from infrastructure.observability.telemetry import current_trace_context

_SENSITIVE_KEY = re.compile(
    r"(?:authorization|cookie|token|secret|password|api[_-]?key|credential)", re.I
)
_CREDENTIAL = re.compile(r"\b(?:bearer|basic)\s+[a-z0-9._~+/-]+=*", re.I)
_QUERY_SECRET = re.compile(
    r"([?&](?:token|secret|password|api[_-]?key|authorization)=[^&#\s]*)", re.I
)
_REDACTED = "[REDACTED]"
_STANDARD_RECORD_FIELDS = frozenset(logging.makeLogRecord({}).__dict__)


def redact(value: Any, key: str | None = None) -> Any:
    """Recursively remove secret-shaped fields and recognizable credentials."""
    if key and _SENSITIVE_KEY.search(key):
        return _REDACTED
    if isinstance(value, Mapping):
        return {
            str(item_key): redact(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [redact(item) for item in value]
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, str):
        value = _CREDENTIAL.sub(_REDACTED, value)
        return _QUERY_SECRET.sub(
            lambda match: match.group(1).split("=", 1)[0] + "=" + _REDACTED, value
        )
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return _REDACTED


class JsonFormatter(logging.Formatter):
    """Serialize safe application fields as one JSON object per stdout line."""

    def __init__(self, service: str, environment: str) -> None:
        super().__init__()
        self._service = service
        self._environment = environment

    def format(self, record: logging.LogRecord) -> str:
        try:
            context = current_trace_context()
            event = getattr(record, "event", record.name)
            payload: dict[str, Any] = {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": record.levelname.lower(),
                "service": self._service,
                "environment": self._environment,
                "event": redact(str(event)),
                "message": redact(record.getMessage()),
            }
            if context:
                payload.update(
                    correlation_id=str(context.correlation_id),
                    trace_id=context.trace_id,
                    span_id=context.span_id,
                )
            for field in ("correlation_id", "trace_id", "span_id", "run_id", "attempt"):
                value = getattr(record, field, None)
                if value is not None:
                    payload[field] = redact(value, field)
            for key, value in record.__dict__.items():
                if key not in _STANDARD_RECORD_FIELDS and key not in payload and key != "event":
                    payload[key] = redact(value, key)
            return json.dumps(payload, default=str, separators=(",", ":"))
        except Exception:
            return (
                '{"level":"error","event":"logging.serialization_failed",'
                '"message":"Safe log serialization failed."}'
            )


def log_event(logger: logging.Logger, level: int, event: str, message: str, **fields: Any) -> None:
    """Emit a named safe operational event without exception or request payloads."""
    logger.log(level, message, extra={"event": event, **redact(fields)})


def configure_logging(settings: Settings, service: str | None = None) -> None:
    """Configure stdout logging once per process, including Uvicorn loggers."""
    if not settings.json_logging_enabled:
        return
    root = logging.getLogger()
    if getattr(root, "_auto_at_json_logging", False):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service or settings.log_service_name, settings.environment))
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"):
        configured = logging.getLogger(name)
        configured.handlers.clear()
        configured.propagate = True
    root._auto_at_json_logging = True  # type: ignore[attr-defined]
