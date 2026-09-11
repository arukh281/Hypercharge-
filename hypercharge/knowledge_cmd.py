"""Unified knowledge query — graph + session + thread state."""

from __future__ import annotations

from pathlib import Path

from hypercharge.context import run_grounded_query
from hypercharge.graph import ensure_graphify_layout, graph_json_path
from hypercharge.grounding_gate import extract_citations
from hypercharge.grounding_session import record_query_success
from hypercharge.session import get_open_chat_entry, peek_current_chat_id

from hypercharge.memory_index import _redact_secrets as _redact_session_line
from hypercharge.memory_index import (
    format_memory_hits,
    index_path,
    rebuild_memory_index,
    search_memory_index,
)
from hypercharge.paths import CURSOR_SESSION


def _section_lines(text: str, heading: str, *, limit: int = 6) -> list[str]:
    """Internal _section_lines. Args: text, heading. Returns: lines. (hypercharge-managed)"""
    lines: list[str] = []
    in_section = False
    for raw in text.splitlines():
        if raw.startswith("## "):
            in_section = raw[3:].strip().lower() == heading.lower()
            continue
        if in_section and raw.strip():
            lines.append(raw.strip())
            if len(lines) >= limit:
                break
    return lines


def _archive_hits(root: Path, question: str, *, limit: int = 5) -> list[str]:
    """Internal _archive_hits. Args: root, question. Returns: hits. (hypercharge-managed)"""
    archive = root / CURSOR_SESSION / "archive"
    if not archive.is_dir():
        return []
    tokens = [t.lower() for t in question.split() if len(t) > 3]
    hits: list[str] = []
    for path in sorted(archive.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:12]:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if tokens and not any(t in text.lower() for t in tokens):
            continue
        for line in text.splitlines():
            line = line.strip()
            if line and (not tokens or any(t in line.lower() for t in tokens)):
                hits.append(f"- {path.name}: {line[:120]} [ARCHIVE]")
                if len(hits) >= limit:
                    return hits
    return hits


def _session_knowledge(root: Path, question: str) -> str:
    """Internal _session_knowledge. Args: root, question. Returns: '\n'.join(parts). (hypercharge-managed)"""
    parts: list[str] = []
    q = question.lower()

    session_path = root / CURSOR_SESSION / "REPO_SESSION.md"
    if session_path.is_file():
        text = session_path.read_text(encoding="utf-8")
        for heading in ("Decisions", "Current initiative", "Activity"):
            section = _section_lines(text, heading)
            hits = [ln for ln in section if not q or any(t in ln.lower() for t in q.split() if len(t) > 3)]
            if hits:
                parts.append(f"## SESSION {heading}")
                parts.extend(f"- {_redact_session_line(ln)} [SESSION]" for ln in hits[:5])

    chat_id = peek_current_chat_id(root)
    if chat_id:
        entry = get_open_chat_entry(root, chat_id)
        parts.append(f"## THREAD {chat_id}")
        parts.append(f"- goal: {entry.get('goal', '—')} [SESSION]")
        for f in (entry.get("files_touched") or [])[:8]:
            parts.append(f"- file: {f} [SESSION]")

    from hypercharge.grounding_session import load_grounding

    grounding = load_grounding(root)
    queried = grounding.get("queried_paths") or []
    if queried:
        parts.append("## SESSION grounded paths")
        for p in queried[-10:]:
            parts.append(f"- {p} [SESSION]")

    archive = _archive_hits(root, question)
    if archive:
        parts.append("## ARCHIVE hits")
        parts.extend(archive)

    memory_hits = search_memory_index(root, question, limit=5)
    if memory_hits:
        parts.append("## MEMORY index")
        parts.extend(format_memory_hits(memory_hits))

    return "\n".join(parts)


def run_knowledge_query(
    root: Path,
    question: str,
    *,
    budget: int = 1500,
    air_gap: bool = False,
) -> tuple[int, str]:
    """Merge graphify digest + session knowledge. Returns (exit_code, text)."""
    root = root.resolve()

    from hypercharge.graph import ensure_graphify_layout, graph_json_path

    ensure_graphify_layout(root)
    graph_json = graph_json_path(root)
    _index_path = index_path(root)
    if graph_json.is_file() and _index_path.is_file():
        if graph_json.stat().st_mtime > _index_path.stat().st_mtime:
            try:
                rebuild_memory_index(root)
            except Exception:
                pass

    sections: list[str] = ["# Hypercharge knowledge query", ""]

    code, graph_text = run_grounded_query(
        root, question, budget=budget, air_gap=air_gap
    )
    sections.append("## Graph")
    sections.append(graph_text)

    if code == 0:
        cites = extract_citations(graph_text)
        record_query_success(root, [p for p, _ in cites])

    session_text = _session_knowledge(root, question)
    if session_text.strip():
        sections.append("")
        sections.append(session_text)

    body = "\n".join(sections).rstrip() + "\n"
    return code, body
