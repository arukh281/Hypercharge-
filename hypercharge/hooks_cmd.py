"""CLI entry for Cursor hook scripts — reads stdin JSON, prints stdout JSON."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from hypercharge.hook_handlers import dispatch_hook
from hypercharge.ui.console import HyperConsole


def run_hook(
    event: str,
    root: Path,
    *,
    stdin_text: str | None = None,
    console: HyperConsole | None = None,
    hook_format: str = "cursor",
) -> int:
    """Run hook. Args: event, root. Returns: 0. (hypercharge-managed)"""
    root = root.resolve()
    raw = stdin_text if stdin_text is not None else sys.stdin.read()

    if hook_format == "claude":
        from hypercharge.claude_hook_adapter import run_claude_hook_stdio

        print(run_claude_hook_stdio(event, root, raw))
        return 0

    payload: dict = {}
    if raw.strip():
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            c = console or HyperConsole(plain=True)
            c.warn("Hook received invalid JSON on stdin")
            if event in ("pre-tool", "preToolUse"):
                print(
                    json.dumps(
                        {
                            "permission": "allow",
                            "agent_message": "Hook stdin was not valid JSON — cannot parse tool input.",
                        }
                    )
                )
                return 0
            print("{}")
            return 0

    result = dispatch_hook(event, root, payload)
    print(json.dumps(result))
    return 0
