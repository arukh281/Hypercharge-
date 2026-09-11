"""Repo manager briefing — orient agents at chat start."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import yaml

from hypercharge.graph import graph_hash, graph_is_present
from hypercharge.graph_freshness import (
    graph_age_days,
    graph_predates_last_commit,
    graph_stale_threshold_days,
)
from hypercharge.paths import CURSOR_SESSION, git_branch
from hypercharge.session import (
    active_open_chats,
    peek_current_chat_id,
    file_overlap,
    load_lock,
)
from hypercharge.ui.console import HyperConsole


def _parse_iso(ts: str) -> datetime | None:
    """Internal _parse_iso. Args: ts. Returns: None. (hypercharge-managed)"""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _section_lines(text: str, heading: str) -> list[str]:
    """Internal _section_lines. Args: text, heading. Returns: lines. (hypercharge-managed)"""
    lines: list[str] = []
    in_section = False
    for raw in text.splitlines():
        if raw.startswith("## "):
            in_section = raw[3:].strip().lower() == heading.lower()
            continue
        if in_section and raw.strip():
            lines.append(raw.strip())
    return lines


def build_brief_text(root: Path) -> str:
    """Assemble plain-text manager briefing for agents."""
    root = root.resolve()
    lines: list[str] = ["# Hypercharge briefing", ""]

    if not (root / ".cursor").is_dir():
        lines.append("Status: Hypercharge not set up — run `hypercharge setup --path <repo_root>`.")
        return "\n".join(lines)

    branch = git_branch(root)
    lock = load_lock(root)
    chat_id = peek_current_chat_id(root) or "(none — run new-chat)"

    lines.append(f"Branch: {branch}")
    lines.append(f"CURRENT_CHAT pointer: {chat_id} (shared — another tab may own a different thread)")
    lines.append("")

    graph_ok = graph_is_present(root)
    gh = graph_hash(root)
    stale_days = graph_stale_threshold_days(root)
    age = graph_age_days(root)
    behind_commits = graph_predates_last_commit(root)
    if graph_ok:
        graph_line = f"Graph: ok ({gh})"
        if behind_commits:
            graph_line += " — STALE: predates last git commit. Run `graphify update .` or `hypercharge wrapup --day` before making structural claims."
        elif age is not None and stale_days is not None and age >= stale_days:
            graph_line += f" — stale ({age}d; refresh on day wrapup or after structural edits)"
        lines.append(graph_line)
    else:
        lines.append("Graph: missing — run `hypercharge setup` or `hypercharge wrapup --day`")
    lines.append("")

    session_path = root / CURSOR_SESSION / "REPO_SESSION.md"
    if session_path.is_file():
        text = session_path.read_text(encoding="utf-8")
        for heading in ("Current initiative", "Decisions", "Constraints", "Activity"):
            section = _section_lines(text, heading)
            if section:
                lines.append(f"## {heading}")
                lines.extend(section[:8])
                lines.append("")

    active = active_open_chats(root)
    ptr_id = peek_current_chat_id(root)
    this_thread = next((c for c in active if c.get("id") == ptr_id), None) if ptr_id else None
    others = [c for c in active if c.get("id") != ptr_id]

    if this_thread:
        lines.append("## This thread (CURRENT_CHAT pointer)")
        lines.append(f"- {this_thread.get('id')}: {this_thread.get('goal', '—')}")
        for q in (this_thread.get("open_questions") or [])[:3]:
            lines.append(f"  ? {q}")
        for f in (this_thread.get("files_touched") or [])[:6]:
            lines.append(f"  → {f}")
        related = this_thread.get("related_to") or []
        if related:
            lines.append(f"  linked: {', '.join(related)}")
        lines.append("")

    if others:
        lines.append("## Other active threads (separate work — do not merge goals)")
        for chat in sorted(others, key=lambda c: c.get("last_active", ""), reverse=True)[:6]:
            cid = chat.get("id", "?")
            goal = chat.get("goal", "—")
            status = chat.get("status", "active")
            la = chat.get("last_active", "")
            lines.append(f"- {cid} ({status}, last {la}): {goal}")
            for q in (chat.get("open_questions") or [])[:2]:
                lines.append(f"  ? {q}")
            for f in (chat.get("files_touched") or [])[:4]:
                lines.append(f"  → {f}")
            related = chat.get("related_to") or []
            if related:
                lines.append(f"  linked: {', '.join(related)}")
        lines.append("")

    overlaps: list[str] = []
    if this_thread and others:
        for other in others:
            shared = file_overlap(this_thread, other)
            if shared:
                overlaps.append(
                    f"- {other.get('id')} ↔ {ptr_id}: {', '.join(shared[:5])}"
                    + (" …" if len(shared) > 5 else "")
                )
    elif len(others) >= 2:
        for i, a in enumerate(others):
            for b in others[i + 1 :]:
                shared = file_overlap(a, b)
                if shared:
                    overlaps.append(
                        f"- {a.get('id')} ↔ {b.get('id')}: {', '.join(shared[:5])}"
                        + (" …" if len(shared) > 5 else "")
                    )

    if overlaps:
        lines.append("## Possible connections (shared files — ask user if related)")
        lines.extend(overlaps[:6])
        lines.append("")
    elif len(active) > 1:
        lines.append("## Parallel work")
        lines.append("- No shared files between active threads — treat as independent unless user says otherwise.")
        lines.append("")

    if active and not this_thread:
        lines.append("## Active threads (pointer not registered — run new-chat or pick a thread)")
        for chat in sorted(active, key=lambda c: c.get("last_active", ""), reverse=True)[:6]:
            lines.append(f"- {chat.get('id')}: {chat.get('goal', '—')}")
        lines.append("")

    last_day = lock.get("last_day_wrapup", "never")
    last_chat = lock.get("last_chat_wrapup", "never")
    lines.append(f"Last day wrapup: {last_day}")
    lines.append(f"Last chat wrapup: {last_chat}")
    lines.append("")

    archive_dir = root / CURSOR_SESSION / "archive"
    if archive_dir.is_dir():
        wraps = sorted(archive_dir.glob("*-wrapup.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if wraps:
            lines.append("## Recent wrapups")
            for p in wraps[:2]:
                excerpt_lines = []
                for raw in p.read_text(encoding="utf-8", errors="replace").splitlines():
                    if raw.strip():
                        excerpt_lines.append(raw.strip())
                    if len(excerpt_lines) >= 10:
                        break
                if excerpt_lines:
                    lines.append(f"### {p.name}")
                    lines.extend(excerpt_lines[:10])
            lines.append("")

    day_wrap = root / CURSOR_SESSION / "LAST_DAY_WRAPUP.md"
    if day_wrap.is_file():
        tail = [ln.strip() for ln in day_wrap.read_text(encoding="utf-8").splitlines() if ln.strip()][-8:]
        if tail:
            lines.append("## Last day wrapup (tail)")
            lines.extend(tail)
            lines.append("")

    lines.append("## Where to look")
    lines.append("- Session truth: `.cursor/session/REPO_SESSION.md`")
    lines.append("- Open work: `.cursor/session/OPEN_CHATS.yaml`")
    lines.append("- Code map: `hypercharge query \"<topic>\"` before repo claims")
    if active:
        top_files = []
        for chat in active:
            top_files.extend(chat.get("files_touched") or [])
        seen: set[str] = set()
        for f in top_files:
            if f not in seen:
                seen.add(f)
                lines.append(f"- Active file: `{f}`")
            if len(seen) >= 8:
                break

    return "\n".join(lines).rstrip() + "\n"


def run_brief(root: Path, console: HyperConsole) -> int:
    """Run brief. Args: root, console. Returns: 0. (hypercharge-managed)"""
    root = root.resolve()
    text = build_brief_text(root)
    print(text)
    if not (root / ".cursor").is_dir():
        console.warn("Run hypercharge setup in this repo first.")
        return 1
    return 0
