"""Setup target — Cursor, Claude Code, or both."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

SetupTarget = Literal["cursor", "claude", "both"]
VALID_TARGETS: frozenset[str] = frozenset({"cursor", "claude", "both"})


def normalize_agent_target(value: str | None, *, default: str = "both") -> str:
    v = (value or default).strip().lower()
    if v not in VALID_TARGETS:
        return default
    return v


def deploys_cursor(target: str) -> bool:
    return normalize_agent_target(target) in ("cursor", "both")


def deploys_claude(target: str) -> bool:
    return normalize_agent_target(target) in ("claude", "both")


def load_agent_target(root: Path, *, default: str = "both") -> str:
    from hypercharge.session import load_repo_profile_json

    profile = load_repo_profile_json(root)
    raw = profile.get("agent_target")
    if isinstance(raw, str) and raw.strip():
        return normalize_agent_target(raw, default=default)
    return normalize_agent_target(default)
