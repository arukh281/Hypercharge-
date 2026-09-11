"""Per-turn delta packet — avoid duplicating full sessionStart context."""

from __future__ import annotations

from pathlib import Path

from hypercharge.graph import graph_hash, graph_is_present, graph_json_path
from hypercharge.paths import CURSOR_SESSION
from hypercharge.session import get_open_chat_entry, peek_current_chat_id
from hypercharge.graph_refresh import pending_count


def _tail_lines(path: Path, *, max_lines: int = 8) -> list[str]:
    """Internal _tail_lines. Args: path. Returns: lines[-max_lines:]. (hypercharge-managed)"""
    if not path.is_file():
        return []
    lines = [ln.rstrip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return lines[-max_lines:]


def _section_lines(text: str, heading: str, *, max_items: int = 4) -> list[str]:
    """Internal _section_lines. Args: text, heading. Returns: lines. (hypercharge-managed)"""
    lines: list[str] = []
    in_section = False
    for raw in text.splitlines():
        if raw.startswith("## "):
            in_section = raw[3:].strip().lower() == heading.lower()
            continue
        if in_section and raw.strip():
            lines.append(raw.strip())
            if len(lines) >= max_items:
                break
    return lines


def _graph_age_days(root: Path) -> int | None:
    """Internal _graph_age_days. Args: root. Returns: int((time.time() - p.stat().st_mtime) / 86400). (hypercharge-managed)"""
    p = graph_json_path(root)
    if not p.is_file():
        return None
    import time

    return int((time.time() - p.stat().st_mtime) / 86400)


def _stale_threshold(root: Path) -> int:
    """Internal _stale_threshold. Args: root. Returns: int((profile.get('graph') or {}).get('stale_after_. (hypercharge-managed)"""
    from hypercharge.inventory import load_repo_profile

    profile = load_repo_profile(root) or {}
    return int((profile.get("graph") or {}).get("stale_after_days", 14))


def build_turn_delta(root: Path, *, budget: int = 400) -> str:
    """Lightweight per-prompt delta — thread state + graph health only."""
    root = root.resolve()
    lines = ["# Hypercharge turn delta", ""]

    chat_id = peek_current_chat_id(root)
    if chat_id:
        entry = get_open_chat_entry(root, chat_id)
        lines.append(f"thread: {chat_id}")
        lines.append(f"goal: {entry.get('goal', '—')}")
        qs = entry.get("open_questions") or []
        if qs:
            lines.append("open_questions: " + "; ".join(qs[:3]))
        touched = entry.get("files_touched") or []
        if touched:
            lines.append("files_touched: " + ", ".join(touched[-6:]))
        chat_path = root / CURSOR_SESSION / "chats" / f"{chat_id}.md"
        chat_tail = _tail_lines(chat_path, max_lines=6)
        if chat_tail:
            lines.append("chat_tail:")
            lines.extend(f"  {ln}" for ln in chat_tail)

    session_path = root / CURSOR_SESSION / "REPO_SESSION.md"
    if session_path.is_file():
        text = session_path.read_text(encoding="utf-8")
        initiative = _section_lines(text, "Current initiative")
        if initiative:
            lines.append("initiative:")
            lines.extend(f"  {ln}" for ln in initiative[:2])
        for heading in ("Decisions", "Activity"):
            section = _section_lines(text, heading)
            if section:
                lines.append(f"{heading.lower()}:")
                lines.extend(f"  {ln}" for ln in section[:3])

    if graph_is_present(root):
        age = _graph_age_days(root)
        gh = graph_hash(root)
        q = pending_count(root)
        stale_days = _stale_threshold(root)
        stale = f" stale {age}d" if age is not None and age >= stale_days else ""
        queue = f" refresh_queue={q}" if q else ""
        lines.append(f"graph: {gh}{stale}{queue}")
    else:
        lines.append("graph: missing (UNVERIFIED grounding)")

    lines.append('action: hypercharge knowledge "<topic>" before repo claims')
    text = "\n".join(lines) + "\n"
    max_chars = max(120, budget * 4)
    if len(text) > max_chars:
        return text[: max_chars - 20] + "\n… [delta clipped]\n"
    return text
