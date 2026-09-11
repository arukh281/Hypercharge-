"""Tier-1 session log — agents patch chat + OPEN_CHATS in one command."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from hypercharge.paths import git_branch
from hypercharge.session import (
    append_decision,
    ensure_session_layout,
    get_open_chat_entry,
    peek_current_chat_id,
    new_chat_id,
    supersede_decision,
    upsert_open_chat,
)
from hypercharge.ui.console import HyperConsole


def _utc_now() -> str:
    """Internal _utc_now. Returns: datetime.now(timezone.utc).replace(microsecond=0).. (hypercharge-managed)"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _patch_open_questions(
    questions: list[str],
    *,
    resolve: str = "",
    defer: str = "",
) -> list[str]:
    """Internal _patch_open_questions. Args: questions. Returns: out. (hypercharge-managed)"""
    out = list(questions)
    if resolve.strip():
        needle = resolve.strip()
        out = [q for q in out if q != needle]
    if defer.strip():
        needle = defer.strip()
        out = [q for q in out if q != needle]
    return out


_COMPLETION_WORDS = frozenset(
    ["wired", "done", "fixed", "closed", "complete", "completed", "resolved", "shipped", "removed", "added"]
)


def _decisions_from_session(root: Path) -> list[str]:
    """Return raw decision lines from ## Decisions in REPO_SESSION.md."""
    session_path = root / ".cursor/session/REPO_SESSION.md"
    if not session_path.is_file():
        return []
    lines: list[str] = []
    in_section = False
    for ln in session_path.read_text(encoding="utf-8").splitlines():
        if ln.startswith("## "):
            in_section = ln[3:].strip().lower() == "decisions"
            continue
        if in_section and ln.strip() and "[SUPERSEDED" not in ln:
            lines.append(ln.strip())
    return lines


def _suggest_decision_supersede(note: str, decisions: list[str]) -> list[str]:
    """Return matching active decision lines that may be resolved by *note*."""
    note_words = set(note.lower().split())
    if not note_words & _COMPLETION_WORDS:
        return []
    suggestions: list[str] = []
    for dec in decisions:
        dec_words = set(dec.lower().split())
        # Overlap beyond common stop-words.
        shared = (note_words & dec_words) - {"the", "a", "an", "to", "in", "of", "and", "is", "it"}
        if len(shared) >= 2:
            suggestions.append(dec)
    return suggestions


def run_log(
    root: Path,
    console: HyperConsole,
    *,
    files: list[str] | None = None,
    note: str = "",
    question: str = "",
    goal: str = "",
    decision: str = "",
    resolve_question: str = "",
    defer_question: str = "",
    supersede: str = "",
) -> int:
    """Run log. Args: root, console. Returns: 0. (hypercharge-managed)"""
    root = root.resolve()
    if not (root / ".cursor").is_dir():
        console.step_fail("Log", "Run hypercharge setup in this repo first.")
        return 1

    ensure_session_layout(root)
    chat_id = peek_current_chat_id(root) or new_chat_id(root)
    chat_path = root / ".cursor/session/chats" / f"{chat_id}.md"

    existing = get_open_chat_entry(root, chat_id)
    touched = list(existing.get("files_touched") or [])
    for f in files or []:
        f = f.strip()
        if f and f not in touched:
            touched.append(f)

    questions = list(existing.get("open_questions") or [])
    if question.strip() and question.strip() not in questions:
        questions.append(question.strip())
    questions = _patch_open_questions(
        questions, resolve=resolve_question, defer=defer_question
    )

    entry_goal = goal.strip() or existing.get("goal", "")
    if not entry_goal and chat_path.is_file():
        for line in chat_path.read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("goal:"):
                entry_goal = line.split(":", 1)[1].strip()

    lines: list[str] = []
    if note.strip():
        lines.append(f"- {_utc_now()}: {note.strip()}")
    if decision.strip():
        lines.append(f"- {_utc_now()}: DECISION: {decision.strip()}")
        append_decision(root, decision.strip())
    if supersede.strip():
        hit = supersede_decision(root, supersede.strip())
        if hit:
            lines.append(f"- {_utc_now()}: SUPERSEDED decision matching: {supersede.strip()}")
        else:
            lines.append(f"- {_utc_now()}: supersede attempted (no match found): {supersede.strip()}")
    if files:
        lines.append(f"- files: {', '.join(files)}")
    if question.strip():
        lines.append(f"- open_question: {question.strip()}")
    if resolve_question.strip():
        lines.append(f"- resolved_question: {resolve_question.strip()}")
    if defer_question.strip():
        lines.append(f"- deferred_question: {defer_question.strip()}")
        deferred_path = root / ".cursor/session/DEFERRED_QUESTIONS.md"
        with deferred_path.open("a", encoding="utf-8") as f:
            f.write(f"- {_utc_now()}: {defer_question.strip()} (chat {chat_id})\n")

    if lines:
        with chat_path.open("a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    try:
        from hypercharge.turn_tracker import record_turn_semantic_log

        record_turn_semantic_log(root, note=note, decision=decision)
    except ImportError:
        pass

    upsert_open_chat(
        root,
        {
            "id": chat_id,
            "branch": existing.get("branch") or git_branch(root),
            "goal": entry_goal or "Active work",
            "open_questions": questions,
            "files_touched": touched,
            "status": existing.get("status", "active"),
        },
    )

    print(f"chat_id: {chat_id}")
    print(f"files_touched: {len(touched)}")
    print(f"open_questions: {len(questions)}")
    if decision.strip():
        print("decision: recorded in REPO_SESSION.md ## Decisions")
    if supersede.strip():
        print("supersede: processed")

    # Phrase detection — surface stale decisions that may be resolved by this note.
    if note.strip() and not supersede.strip():
        active_decisions = _decisions_from_session(root)
        matches = _suggest_decision_supersede(note.strip(), active_decisions)
        if matches:
            print("\n[HYPERCHARGE-DECISION-HINT]")
            print("Your note looks like it may resolve existing decision(s):")
            for m in matches[:3]:
                print(f"  • {m}")
            print("To mark as superseded:")
            print(f'  hypercharge log --supersede "<matching text>"')
            print("[/HYPERCHARGE-DECISION-HINT]")

    try:
        from hypercharge.memory_index import append_memory_chunk

        if decision.strip():
            append_memory_chunk(
                root,
                "decision",
                ".cursor/session/REPO_SESSION.md",
                decision.strip(),
            )
        elif note.strip() and not note.strip().startswith("auto:"):
            append_memory_chunk(
                root,
                "chat",
                f".cursor/session/chats/{chat_id}.md",
                note.strip(),
            )
    except OSError:
        pass

    return 0
