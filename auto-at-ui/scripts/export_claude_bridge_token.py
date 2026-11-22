"""Copy only the current Claude Code OAuth access token for the local claude-bridge.

The refresh token never leaves the host credential file, so the container cannot
rotate the user's login. The access token expires (hours); rerun this script, or
write a long-lived token from `claude setup-token` to the same file instead.
Nothing is printed except the expiry time.

    uv run python scripts/export_claude_bridge_token.py <private-directory>
"""

import json
import os
import sys
import time
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    target_dir = Path(sys.argv[1]).expanduser().resolve()
    source = Path.home() / ".claude" / ".credentials.json"
    oauth = json.loads(source.read_text(encoding="utf-8"))["claudeAiOauth"]
    remaining_hours = (oauth["expiresAt"] / 1000 - time.time()) / 3600
    if remaining_hours <= 0:
        print("access token expired; run any `claude` command to refresh, then retry")
        return 1
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "claude-oauth-token"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(oauth["accessToken"], encoding="utf-8")
    os.replace(temporary, target)  # bind-mount the directory, so replacement is visible
    print(f"wrote {target.name}; access token expires in {remaining_hours:.1f} h")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
