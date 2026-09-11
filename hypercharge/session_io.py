"""Shared session file helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def section_lines(text: str, heading: str) -> list[str]:
    lines: list[str] = []
    in_section = False
    for raw in text.splitlines():
        if raw.startswith("## "):
            in_section = raw[3:].strip().lower() == heading.lower()
            continue
        if in_section and raw.strip():
            lines.append(raw.strip())
    return lines


def chat_file_excerpt(root: Path, chat_id: str, *, max_lines: int = 24) -> list[str]:
    """Recent non-header lines from a chat scratchpad."""
    p = root / ".cursor/session/chats" / f"{chat_id}.md"
    if not p.is_file():
        return []
    body = [
        ln.strip()
        for ln in p.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.startswith("#")
    ]
    return body[-max_lines:]
