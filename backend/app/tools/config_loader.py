from __future__ import annotations

"""
tools/config_loader.py
──────────────────────
Environment configuration loader for the Execution pipeline stage.

Used by the `env_adapter` agent (execution crew) to resolve the target
test environment's base URL, auth tokens, and custom headers before
the test_runner agent executes API calls.

Resolution order (highest → lowest priority):
    1. Explicit ``config_file`` path (JSON)
    2. ``./configs/<environment>.json``
    3. Environment variables prefixed with ``TEST_ENV_``
    4. Well-known env vars: TEST_BASE_URL, TEST_AUTH_TOKEN
    5. Built-in defaults

When crewai is installed, ``ConfigLoaderTool`` is also exported as a
``crewai.tools.BaseTool`` subclass so the env_adapter agent can call it
autonomously during task execution.

Usage (plain Python)::

    from app.tools.config_loader import load_env_config

    config = load_env_config("staging")
    print(config["base_url"])   # e.g. "https://staging-api.example.com"

Usage (CrewAI tool)::

    from app.tools.config_loader import ConfigLoaderTool

    tool = ConfigLoaderTool()
    result = tool.run({"environment": "staging"})
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Optional CrewAI import ────────────────────────────────────────────────────
try:
    from crewai.tools import BaseTool  # type: ignore[import-untyped]
    from pydantic import BaseModel, Field

    _CREWAI_AVAILABLE = True
except ImportError:
    BaseTool = object  # type: ignore[assignment,misc]
    _CREWAI_AVAILABLE = False

# ─────────────────────────────────────────────────────────────────────────────
# Default config structure
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_CONFIG: dict[str, Any] = {
    "environment": "default",
    "base_url": None,
    "auth_token": None,
    "auth_type": "Bearer",  # Bearer | Basic | ApiKey | None
    "api_key_header": "X-Api-Key",  # header name when auth_type == ApiKey
    "timeout_seconds": 30,
    "retry_count": 3,
    "retry_delay_seconds": 1,
    "headers": {},
    "tls_verify": True,
    "proxy": None,
}

# Well-known environment variable names
_KNOWN_ENV_VARS: dict[str, str] = {
    "TEST_BASE_URL": "base_url",
    "TEST_AUTH_TOKEN": "auth_token",
    "TEST_AUTH_TYPE": "auth_type",
    "TEST_API_KEY": "auth_token",
    "TEST_TIMEOUT": "timeout_seconds",
    "TEST_TLS_VERIFY": "tls_verify",
    "TEST_PROXY": "proxy",
}


# ─────────────────────────────────────────────────────────────────────────────
# Public functions
# ─────────────────────────────────────────────────────────────────────────────


def load_env_config(
    environment: str = "default",
    config_file: Optional[str] = None,
    config_dir: str = "configs",
) -> dict[str, Any]:
    """
    Load test-environment configuration and return a fully resolved config dict.

    Resolution order (first match wins for each key):
        1. Explicit ``config_file`` (JSON file path)
        2. ``<config_dir>/<environment>.json``
        3. Environment variables with prefix ``TEST_ENV_``
        4. Well-known env vars (TEST_BASE_URL, TEST_AUTH_TOKEN, …)
        5. Built-in defaults

    Args:
        environment:  Logical environment name (e.g. "default", "staging",
                      "production"). Used to locate the auto-discovered JSON
                      file and stored in the returned config.
        config_file:  Optional explicit path to a JSON configuration file.
                      When provided, *all* keys in that file override defaults.
        config_dir:   Directory to search for ``<environment>.json`` files.
                      Defaults to ``configs/`` relative to the current working
                      directory.

    Returns:
        A fully resolved configuration dict with at least these keys:
        ``environment``, ``base_url``, ``auth_token``, ``auth_type``,
        ``timeout_seconds``, ``retry_count``, ``headers``, ``tls_verify``.

    Raises:
        Nothing — all errors are logged and the function falls back gracefully.
    """
    config: dict[str, Any] = {**_DEFAULT_CONFIG, "environment": environment}

    # ── 1. Explicit config file ───────────────────────────────────────────────
    if config_file:
        _try_load_json(Path(config_file), config, source="explicit config_file")
        _post_process(config)
        logger.info(
            "Loaded config for '%s' from explicit file: %s",
            environment,
            config_file,
        )
        return config

    # ── 2. Auto-discovered <config_dir>/<environment>.json ────────────────────
    auto_path = Path(config_dir) / f"{environment}.json"
    if auto_path.exists():
        _try_load_json(auto_path, config, source=f"auto-discovered {auto_path}")

    # ── 3. TEST_ENV_* env vars (override any file values) ────────────────────
    prefix = "TEST_ENV_"
    for key, value in os.environ.items():
        if key.startswith(prefix):
            config_key = key[len(prefix) :].lower()
            config[config_key] = _coerce_env_value(config_key, value)
            logger.debug("Set config[%r] from env var %r", config_key, key)

    # ── 4. Well-known env vars ────────────────────────────────────────────────
    for env_var, config_key in _KNOWN_ENV_VARS.items():
        value = os.getenv(env_var)
        if value:
            config[config_key] = _coerce_env_value(config_key, value)
            logger.debug(
                "Set config[%r] from well-known env var %r", config_key, env_var
            )

    # ── Post-processing (build auth headers, etc.) ────────────────────────────
    _post_process(config)

    logger.info(
        "Resolved env config for '%s': base_url=%s, auth_type=%s",
        environment,
        config.get("base_url") or "(not set)",
        config.get("auth_type"),
    )
    return config


def build_auth_headers(config: dict[str, Any]) -> dict[str, str]:
    """
    Build HTTP authentication headers from a resolved config dict.

    Supports:
        - ``Bearer`` token  → ``Authorization: Bearer <token>``
        - ``Basic`` auth    → ``Authorization: Basic <token>``
        - ``ApiKey``        → ``<api_key_header>: <token>``
        - ``None``          → empty dict

    Args:
        config: Resolved config dict from :func:`load_env_config`.

    Returns:
        Dict of header name → header value ready to merge into request headers.
    """
    token = config.get("auth_token")
    auth_type = (config.get("auth_type") or "Bearer").strip()

    if not token:
        return {}

    if auth_type.lower() in ("bearer", "basic"):
        return {"Authorization": f"{auth_type} {token}"}

    if auth_type.lower() == "apikey":
        header_name = config.get("api_key_header") or "X-Api-Key"
        return {header_name: token}

    # Unknown auth type — omit auth headers
    logger.warning("Unknown auth_type %r — skipping auth header", auth_type)
    return {}


def merge_headers(config: dict[str, Any]) -> dict[str, str]:
    """
    Return the complete set of headers to use for requests:
    ``config["headers"]`` merged with auth headers from :func:`build_auth_headers`.
    Auth headers take precedence over custom headers.

    Args:
        config: Resolved config dict.

    Returns:
        Merged header dict.
    """
    base: dict[str, str] = dict(config.get("headers") or {})
    auth = build_auth_headers(config)
    return {**base, **auth}


def list_available_environments(config_dir: str = "configs") -> list[str]:
    """
    Return the list of environment names that have a JSON config file in
    *config_dir*.  Also includes ``"default"`` unconditionally.

    Returns:
        Sorted list of environment names (without the ``.json`` extension).
    """
    envs = {"default"}
    config_path = Path(config_dir)
    if config_path.is_dir():
        for p in config_path.glob("*.json"):
            envs.add(p.stem)
    return sorted(envs)


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


def _try_load_json(path: Path, config: dict[str, Any], source: str) -> None:
    """Load a JSON file into *config* in-place, logging any errors."""
    try:
        file_config: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(file_config, dict):
            logger.warning("Config file %r is not a JSON object — ignoring", source)
            return
        config.update(file_config)
        logger.debug("Loaded config from %s", source)
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse config file (%s): %s", source, exc)
    except OSError as exc:
        logger.warning("Cannot read config file (%s): %s", source, exc)


def _coerce_env_value(key: str, value: str) -> Any:
    """
    Attempt to coerce a string environment-variable value to a sensible Python
    type based on the config key name.

    - Boolean keys (tls_verify): "true" / "false" → bool
    - Numeric keys (timeout_seconds, retry_count): → int
    - Everything else: str
    """
    lower = value.strip().lower()

    # Boolean
    if key in ("tls_verify",):
        return lower not in ("false", "0", "no", "off")

    # Integer
    if key in ("timeout_seconds", "retry_count", "retry_delay_seconds"):
        try:
            return int(value)
        except ValueError:
            return value

    return value


def _post_process(config: dict[str, Any]) -> None:
    """
    Normalise the config dict in-place after all sources have been applied:
    - Strip trailing slash from base_url
    - Ensure ``headers`` is a dict
    - Add computed ``auth_headers`` key
    """
    # Normalise base_url
    base_url = config.get("base_url")
    if isinstance(base_url, str):
        config["base_url"] = base_url.rstrip("/")

    # Ensure headers is a dict
    if not isinstance(config.get("headers"), dict):
        config["headers"] = {}

    # Pre-compute auth_headers (convenient for the env_adapter agent)
    config["auth_headers"] = build_auth_headers(config)


# ─────────────────────────────────────────────────────────────────────────────
# CrewAI BaseTool wrapper (only available when crewai is installed)
# ─────────────────────────────────────────────────────────────────────────────

if _CREWAI_AVAILABLE:
    from pydantic import BaseModel, Field  # re-import for scoping clarity

    class ConfigLoaderInput(BaseModel):
        environment: str = Field(
            default="default",
            description=(
                "Target environment name: 'default', 'staging', 'production', etc. "
                "Must match a file in the configs/ directory or be resolvable from "
                "TEST_BASE_URL / TEST_AUTH_TOKEN environment variables."
            ),
        )
        config_file: Optional[str] = Field(
            default=None,
            description=(
                "Optional explicit path to a JSON configuration file. "
                "When provided, this file overrides all other config sources."
            ),
        )
        config_dir: str = Field(
            default="configs",
            description="Directory to search for <environment>.json config files.",
        )

    class ConfigLoaderTool(BaseTool):  # type: ignore[misc,valid-type]
        """
        CrewAI tool: loads test-environment configuration.

        The env_adapter agent uses this tool to resolve the target base URL,
        authentication headers, and other per-environment settings before
        the test_runner executes any API calls.
        """

        name: str = "config_loader"
        description: str = (
            "Load test environment configuration for a given environment name "
            "(default / staging / production / …). "
            "Returns a JSON object with: environment, base_url, auth_token, "
            "auth_type, auth_headers, timeout_seconds, retry_count, headers, "
            "tls_verify. Use this before executing any API test calls to ensure "
            "the correct base URL and authentication are applied."
        )
        args_schema: type[BaseModel] = ConfigLoaderInput

        def _run(
            self,
            environment: str = "default",
            config_file: Optional[str] = None,
            config_dir: str = "configs",
        ) -> str:
            config = load_env_config(
                environment=environment,
                config_file=config_file,
                config_dir=config_dir,
            )
            # Redact auth token in the response to avoid leaking credentials
            # in CrewAI logs while still conveying whether auth is configured.
            safe_config = {
                **config,
                "auth_token": "***" if config.get("auth_token") else None,
                "auth_headers": {
                    k: (v[:4] + "***" if len(v) > 8 else "***")
                    for k, v in (config.get("auth_headers") or {}).items()
                },
            }
            return json.dumps(safe_config, indent=2, default=str)

else:
    # Provide a clear error message when crewai is absent so the user knows
    # what to install — without crashing at import time.
    class ConfigLoaderTool:  # type: ignore[no-redef]
        """Stub — crewai is not installed."""

        def __init__(self, *args: object, **kwargs: object) -> None:
            raise ImportError(
                "crewai is not installed. "
                "ConfigLoaderTool requires crewai. "
                "Run: uv add crewai  (Linux/macOS)  or use Docker/WSL2 on Windows."
            )
