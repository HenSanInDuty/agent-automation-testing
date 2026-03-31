from __future__ import annotations

"""
tools/api_runner.py
───────────────────
HTTP API execution tool for the Execution crew's test_runner agent.

Provides two interfaces:
  1. ``run_api_request()`` – plain Python function, usable without CrewAI.
  2. ``APIRunnerTool``     – CrewAI ``BaseTool`` subclass; only defined when
                             crewai is installed.

Usage (plain)::

    from app.tools.api_runner import run_api_request

    result = run_api_request(
        url="https://api.example.com/v1/users",
        method="POST",
        headers={"Content-Type": "application/json"},
        body={"username": "alice", "email": "alice@example.com"},
        expected_status=201,
    )
    # result["success"] → True/False
    # result["status_code"] → 201
    # result["body"] → {...}

Usage (CrewAI tool)::

    from app.tools.api_runner import APIRunnerTool
    tool = APIRunnerTool()
    agent = Agent(..., tools=[tool])
"""

import json
import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Optional dependencies ─────────────────────────────────────────────────────

try:
    import httpx  # type: ignore[import-untyped]

    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

try:
    from crewai.tools import BaseTool  # type: ignore[import-untyped]
    from pydantic import BaseModel, Field

    _CREWAI_AVAILABLE = True
except ImportError:
    BaseTool = object  # type: ignore[assignment,misc]
    _CREWAI_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
# Result model (plain dict – no Pydantic dependency for callers)
# ─────────────────────────────────────────────────────────────────────────────


def _empty_result(error: str, duration_ms: float = 0.0) -> dict[str, Any]:
    return {
        "status_code": None,
        "body": None,
        "headers": {},
        "duration_ms": round(duration_ms, 2),
        "success": False,
        "error": error,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Core execution function
# ─────────────────────────────────────────────────────────────────────────────


def run_api_request(
    url: str,
    method: str = "GET",
    headers: Optional[dict[str, str]] = None,
    body: Optional[dict[str, Any] | str | list] = None,
    query_params: Optional[dict[str, str]] = None,
    timeout: int = 30,
    expected_status: Optional[int] = None,
    follow_redirects: bool = True,
    verify_ssl: bool = True,
) -> dict[str, Any]:
    """
    Execute a single HTTP request and return a structured result dictionary.

    Args:
        url:              Full URL to call.
        method:           HTTP verb – GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS.
        headers:          Additional request headers.
        body:             Request body.  A ``dict`` is sent as JSON;
                          a ``str`` is sent as raw bytes (utf-8).
                          Ignored for GET / HEAD / DELETE by default.
        query_params:     URL query-string parameters.
        timeout:          Request timeout in seconds.
        expected_status:  When set, ``success`` will be ``True`` only if the
                          actual status code matches this value.
        follow_redirects: Whether to follow HTTP redirects (default True).
        verify_ssl:       Whether to verify TLS certificates (default True).

    Returns:
        A dict with keys:

        .. code-block:: text

            status_code   int | None   – HTTP status code (None on network error)
            body          Any          – Parsed JSON or raw text (None on error)
            headers       dict         – Response headers
            duration_ms   float        – Round-trip time in milliseconds
            success       bool         – True if request succeeded (and status matched)
            error         str | None   – Error message if the request failed

    Raises:
        Nothing – all exceptions are caught and returned in the ``error`` field.
    """
    if not _HTTPX_AVAILABLE:
        return _empty_result(
            "httpx is not installed. Run: uv add httpx",
        )

    method = method.upper()
    headers = dict(headers or {})
    t0 = time.monotonic()

    try:
        # Build request kwargs
        request_kwargs: dict[str, Any] = {
            "method": method,
            "url": url,
            "headers": headers,
            "timeout": timeout,
            "follow_redirects": follow_redirects,
        }

        if query_params:
            request_kwargs["params"] = query_params

        # Attach body for mutating methods
        if body is not None and method not in ("GET", "HEAD", "DELETE", "OPTIONS"):
            if isinstance(body, (dict, list)):
                request_kwargs["json"] = body
                # httpx sets Content-Type automatically for json=
            elif isinstance(body, str):
                request_kwargs["content"] = body.encode("utf-8")
                headers.setdefault("Content-Type", "text/plain; charset=utf-8")
            else:
                request_kwargs["content"] = body  # bytes

        with httpx.Client(verify=verify_ssl) as client:
            response = client.request(**request_kwargs)

        duration_ms = (time.monotonic() - t0) * 1000

        # Parse response body
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                response_body: Any = response.json()
            except Exception:
                response_body = response.text
        else:
            response_body = response.text

        # Determine success
        if expected_status is not None:
            success = response.status_code == expected_status
        else:
            # Treat 2xx as success
            success = 200 <= response.status_code < 300

        logger.debug(
            "API %s %s → %d  (%.1f ms)",
            method,
            url,
            response.status_code,
            duration_ms,
        )

        return {
            "status_code": response.status_code,
            "body": response_body,
            "headers": dict(response.headers),
            "duration_ms": round(duration_ms, 2),
            "success": success,
            "error": None,
        }

    except httpx.TimeoutException as exc:
        duration_ms = (time.monotonic() - t0) * 1000
        msg = f"Request timed out after {timeout}s: {exc}"
        logger.warning("API runner timeout: %s %s – %s", method, url, msg)
        return _empty_result(msg, duration_ms)

    except httpx.ConnectError as exc:
        duration_ms = (time.monotonic() - t0) * 1000
        msg = f"Connection error: {exc}"
        logger.warning("API runner connect error: %s %s – %s", method, url, msg)
        return _empty_result(msg, duration_ms)

    except Exception as exc:  # pragma: no cover
        duration_ms = (time.monotonic() - t0) * 1000
        msg = f"Unexpected error: {type(exc).__name__}: {exc}"
        logger.exception("API runner unexpected error: %s %s", method, url)
        return _empty_result(msg, duration_ms)


def run_api_requests_batch(
    requests: list[dict[str, Any]],
    stop_on_failure: bool = False,
) -> list[dict[str, Any]]:
    """
    Execute a list of API requests sequentially and return all results.

    Each item in *requests* should be a dict accepted by
    :func:`run_api_request` as ``**kwargs``.

    Args:
        requests:         List of request parameter dicts.
        stop_on_failure:  If True, stop after the first unsuccessful request.

    Returns:
        List of result dicts in the same order as *requests*.
    """
    results: list[dict[str, Any]] = []
    for req in requests:
        result = run_api_request(**req)
        results.append(result)
        if stop_on_failure and not result["success"]:
            logger.info(
                "run_api_requests_batch: stopping after failure on %s %s",
                req.get("method", "GET"),
                req.get("url", ""),
            )
            break
    return results


# ─────────────────────────────────────────────────────────────────────────────
# CrewAI Tool wrapper (only defined when crewai is installed)
# ─────────────────────────────────────────────────────────────────────────────

if _CREWAI_AVAILABLE:

    class _APIRunnerInput(BaseModel):  # type: ignore[misc]
        url: str = Field(
            description="Full URL to call (e.g. https://api.example.com/v1/users)"
        )
        method: str = Field(
            default="GET",
            description="HTTP verb: GET | POST | PUT | PATCH | DELETE",
        )
        headers: dict[str, str] = Field(
            default_factory=dict,
            description="Additional HTTP headers as key-value pairs",
        )
        body: Optional[Any] = Field(
            default=None,
            description=(
                "Request body. Pass a JSON-serialisable dict for JSON payloads "
                "or a string for raw body. Ignored for GET/HEAD requests."
            ),
        )
        query_params: Optional[dict[str, str]] = Field(
            default=None,
            description="URL query-string parameters as key-value pairs",
        )
        timeout: int = Field(
            default=30,
            description="Request timeout in seconds (default 30)",
        )
        expected_status_code: Optional[int] = Field(
            default=None,
            description=(
                "Expected HTTP status code. When provided, success=True only "
                "if the actual code matches. Omit to use 2xx-is-success logic."
            ),
        )

    class APIRunnerTool(BaseTool):  # type: ignore[misc,valid-type]
        """
        CrewAI tool that executes HTTP API requests.

        Designed for use by the ``test_runner`` and ``execution_orchestrator``
        agents in the Execution crew.
        """

        name: str = "api_runner"
        description: str = (
            "Execute an HTTP API request (GET, POST, PUT, PATCH, DELETE) and return "
            "a structured JSON result with status code, response body, headers, "
            "timing, success flag, and any error message. "
            "Use this tool to call real API endpoints during test execution."
        )
        args_schema: type[BaseModel] = _APIRunnerInput  # type: ignore[assignment]

        def _run(
            self,
            url: str,
            method: str = "GET",
            headers: dict[str, str] | None = None,
            body: Any = None,
            query_params: dict[str, str] | None = None,
            timeout: int = 30,
            expected_status_code: int | None = None,
        ) -> str:
            """Execute the API request and return JSON-formatted result."""
            result = run_api_request(
                url=url,
                method=method,
                headers=headers or {},
                body=body,
                query_params=query_params,
                timeout=timeout,
                expected_status=expected_status_code,
            )
            return json.dumps(result, indent=2, default=str)

else:
    # Provide a helpful stub so imports don't fail when crewai is absent

    class APIRunnerTool:  # type: ignore[no-redef]
        """Stub – crewai is not installed.  Install crewai to use this tool."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError(
                "APIRunnerTool requires crewai. "
                "On Linux/macOS: uv add crewai. "
                "On Windows: use Docker or WSL2."
            )
