"""Process-global agent-session scope — namespaces per-session state files.

Each Claude Code hook runs as a fresh OS process, so a module-level global set
once at the hook entry point is race-free: the race we fix is between separate
processes (parallel Claude windows or subagents) writing the *same* state file,
not concurrency within a single process. When no session id is known (the CLI,
the MCP server, or the Cursor hook path), callers fall back to the legacy
shared per-repo file, preserving existing behaviour.
"""

from __future__ import annotations

import os
import re

_SESSION_ID: str | None = None
_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]")


def set_session_id(session_id: str | None) -> None:
    """Record the current agent session id for this hook process."""
    global _SESSION_ID
    sid = (session_id or "").strip()
    _SESSION_ID = sid or None


def current_session_id() -> str | None:
    """Explicitly-set session id, else the HYPERCHARGE_SESSION_ID env, else None."""
    if _SESSION_ID:
        return _SESSION_ID
    env = (os.environ.get("HYPERCHARGE_SESSION_ID") or "").strip()
    return env or None


def session_slug() -> str | None:
    """Filesystem-safe single-component slug for the current session, or None.

    Strips leading/trailing dots and dashes so a hostile id like ``..`` cannot
    resolve to a parent directory.
    """
    sid = current_session_id()
    if not sid:
        return None
    slug = _UNSAFE.sub("-", sid).strip("-.")
    return slug[:64] or None
