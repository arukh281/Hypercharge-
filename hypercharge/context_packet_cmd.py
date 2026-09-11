"""Bounded context packet — compiled digest for agent turns."""

from __future__ import annotations

import json
from pathlib import Path

from hypercharge.graph import graph_hash, graph_is_present
from hypercharge.session import peek_current_chat_id, get_open_chat_entry
from hypercharge.paths import CURSOR_SESSION


def _tail_lines(path: Path, *, max_lines: int = 12) -> list[str]:
    """Internal _tail_lines. Args: path. Returns: lines[-max_lines:]. (hypercharge-managed)"""
    if not path.is_file():
        return []
    lines = [ln.rstrip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return lines[-max_lines:]


def _section_lines(text: str, heading: str, *, max_items: int = 6) -> list[str]:
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


def build_context_packet(root: Path, *, budget: int = 800, lean: bool = False) -> str:
    """Compile session + graph state into one bounded digest."""
    root = root.resolve()
    parts: list[str] = ["# Hypercharge context packet", ""]

    if not (root / ".cursor").is_dir():
        parts.append("UNVERIFIED — run hypercharge setup first.")
        return _clip("\n".join(parts), budget)

    chat_id = peek_current_chat_id(root)
    entry: dict = {}
    if chat_id:
        entry = get_open_chat_entry(root, chat_id)
        parts.append(f"thread: {chat_id}")
        parts.append(f"goal: {entry.get('goal', '—')}")
        qs = entry.get("open_questions") or []
        if qs:
            parts.append("open_questions:")
            for q in qs[:3 if lean else 4]:
                parts.append(f"  ? {q}")
        touched = entry.get("files_touched") or []
        if touched:
            parts.append("files_touched: " + ", ".join(touched[:4 if lean else 6]))
        if not lean:
            chat_path = root / CURSOR_SESSION / "chats" / f"{chat_id}.md"
            chat_tail = _tail_lines(chat_path, max_lines=10)
            if chat_tail:
                parts.append("chat_tail:")
                parts.extend(f"  {ln}" for ln in chat_tail)
        parts.append("")

    gh = graph_hash(root) if graph_is_present(root) else "missing"
    parts.append(f"graph: {gh}")
    parts.append("")

    session_path = root / CURSOR_SESSION / "REPO_SESSION.md"
    if session_path.is_file():
        text = session_path.read_text(encoding="utf-8")
        max_items = 3 if lean else 5
        for heading in ("Decisions", "Current initiative", "Activity"):
            section = _section_lines(text, heading, max_items=max_items)
            if section:
                parts.append(f"## {heading}")
                parts.extend(section[:max_items])
                parts.append("")

    if not lean:
        deferred_path = root / CURSOR_SESSION / "DEFERRED_QUESTIONS.md"
        deferred_tail = _tail_lines(deferred_path, max_lines=5)
        if deferred_tail:
            parts.append("## Deferred questions")
            parts.extend(deferred_tail)
            parts.append("")

        day_wrap = root / CURSOR_SESSION / "LAST_DAY_WRAPUP.md"
        tail = _tail_lines(day_wrap, max_lines=8)
        if tail:
            parts.append("## Last day (tail)")
            parts.extend(tail)
            parts.append("")

        archive = root / CURSOR_SESSION / "archive"
        if archive.is_dir():
            wraps = sorted(archive.glob("*-wrapup.md"), key=lambda p: p.stat().st_mtime, reverse=True)
            if wraps:
                excerpt_lines = _tail_lines(wraps[0], max_lines=8)
                if excerpt_lines:
                    parts.append(f"## Recent wrapup ({wraps[0].name})")
                    parts.extend(excerpt_lines)
                    parts.append("")

    parts.append('ground: hypercharge knowledge "<topic>" before repo claims (exit 0 required)')

    if not lean:
        recall_q = ""
        if chat_id:
            recall_q = str(entry.get("goal") or "")
        if session_path.is_file() and not recall_q:
            initiative = _section_lines(session_path.read_text(encoding="utf-8"), "Current initiative")
            if initiative:
                recall_q = initiative[0]
        if recall_q:
            from hypercharge.memory_index import format_memory_hits, search_memory_index

            hits = search_memory_index(root, recall_q, limit=3)
            if hits:
                parts.append("")
                parts.append("## MEMORY recall")
                parts.extend(format_memory_hits(hits))

    return _clip("\n".join(parts).rstrip() + "\n", budget)


def _clip(text: str, budget: int) -> str:
    """Rough char budget (tokens ≈ chars/4 for English prose)."""
    max_chars = max(200, budget * 4)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 30] + "\n… [packet truncated] …\n"


def run_context_packet(root: Path, *, budget: int = 800, as_json: bool = False) -> int:
    """Run context packet. Args: root. Returns: 0. (hypercharge-managed)"""
    packet = build_context_packet(root, budget=budget)
    if as_json:
        print(json.dumps({"budget": budget, "packet": packet}, indent=2))
    else:
        print(packet)
    return 0
