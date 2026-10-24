"""Build-time tool metadata override; preserve the pinned CLI's model and prompts."""

import json
import subprocess
from copy import deepcopy
from pathlib import Path

from agents.prompts.codex_exploration import INSTRUCTIONS
from domain.codex_bridge import CLI_VERSION

CATALOGUE_PATH = Path("/app/codex-model-catalogue.json")
INSTRUCTIONS_PATH = Path("/app/codex-proposal-instructions.txt")


def restricted_catalogue(bundled: dict) -> dict:
    models = [model for model in bundled["models"] if model["slug"] == "gpt-6-luna"]
    if len(models) != 1:
        raise ValueError("expected exactly one bundled Luna model")
    model = deepcopy(models[0])
    # Luna's code_mode_only overrides features.code_mode=false. Removing these
    # tool capabilities changes no model identity, prompt, or sampling metadata.
    model.update(tool_mode=None, apply_patch_tool_type=None, experimental_supported_tools=[])
    return {"models": [model]}


def bundled_catalogue(executable: str) -> dict:
    result = subprocess.run(
        [executable, "debug", "models", "--bundled"],
        capture_output=True, text=True, check=True, timeout=10,
        env={"HOME": "/bridge-home", "CODEX_HOME": "/bridge-home/.codex",
             "PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8"},
    )
    return restricted_catalogue(json.loads(result.stdout))


def validate_catalogue(executable: str) -> None:
    if CATALOGUE_PATH.is_symlink() or not CATALOGUE_PATH.is_file():
        raise ValueError("missing immutable model catalogue")
    if json.loads(CATALOGUE_PATH.read_text()) != bundled_catalogue(executable):
        raise ValueError("model catalogue differs from pinned bundled metadata")


def validate_instructions() -> None:
    if (INSTRUCTIONS_PATH.is_symlink() or not INSTRUCTIONS_PATH.is_file()
            or INSTRUCTIONS_PATH.read_text() != INSTRUCTIONS):
        raise ValueError("missing or changed centralized proposal instructions")


if __name__ == "__main__":
    executable = "/usr/local/bin/codex"
    version = subprocess.run(
        [executable, "--version"], capture_output=True, text=True, check=True, timeout=10,
    )
    if version.stdout.strip() != f"codex-cli {CLI_VERSION}":
        raise ValueError("unexpected CLI version")
    CATALOGUE_PATH.write_text(json.dumps(bundled_catalogue(executable)), encoding="utf-8")
    CATALOGUE_PATH.chmod(0o444)
    INSTRUCTIONS_PATH.write_text(INSTRUCTIONS, encoding="utf-8")
    INSTRUCTIONS_PATH.chmod(0o444)
