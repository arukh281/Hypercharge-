"""Scan repo for loose ends — open questions, stale threads, graph gaps."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from hypercharge.graph import graph_hash, graph_json_path, graph_is_present
from hypercharge.paths import CURSOR_HYPERCHARGE, CURSOR_SESSION, git_branch
from hypercharge.session import active_open_chats, current_chat_id, load_lock, load_repo_profile_json


@dataclass(frozen=True)
class LooseEnd:
    """One actionable gap the user or agent should resolve."""

    id: str
    kind: str
    message: str
    chat_id: str | None = None
    suggested: str = ""
    user_surface: bool = True
    user_prompt: str = ""


def _parse_iso(ts: str) -> datetime | None:
    """Internal _parse_iso. Args: ts. Returns: None. (hypercharge-managed)"""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _days_since(ts: str) -> int | None:
    """Internal _days_since. Args: ts. Returns: (datetime.now(timezone.utc) - dt).days. (hypercharge-managed)"""
    dt = _parse_iso(ts)
    if not dt:
        return None
    return (datetime.now(timezone.utc) - dt).days


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


def _profile_thresholds(root: Path) -> tuple[int, int]:
    """Internal _profile_thresholds. Args: root. Returns: (int(session_days), int(graph_days)). (hypercharge-managed)"""
    profile = load_repo_profile_json(root)
    session_days = (profile.get("session") or {}).get("stale_after_days", 14)
    graph_days = (profile.get("graph") or {}).get("stale_after_days", 14)
    return int(session_days), int(graph_days)


def _onboard_age_days(root: Path) -> int | None:
    """Internal _onboard_age_days. Args: root. Returns: (datetime.now(timezone.utc) - mtime).days. (hypercharge-managed)"""
    path = root / CURSOR_HYPERCHARGE / "last-onboard.json"
    if not path.is_file():
        return None
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return (datetime.now(timezone.utc) - mtime).days


def _repo_has_decisions(root: Path) -> bool:
    """Internal _repo_has_decisions. Args: root. Returns: bool(_section_lines(text, 'Decisions')). (hypercharge-managed)"""
    session_path = root / CURSOR_SESSION / "REPO_SESSION.md"
    if not session_path.is_file():
        return False
    text = session_path.read_text(encoding="utf-8")
    return bool(_section_lines(text, "Decisions"))


def collect_loose_ends(root: Path) -> list[LooseEnd]:
    """Return ordered loose ends for start-day and enforcement checks."""
    root = root.resolve()
    ends: list[LooseEnd] = []
    n = 0

    def add(
        kind: str,
        message: str,
        *,
        chat_id: str | None = None,
        suggested: str = "",
        user_surface: bool = True,
        user_prompt: str = "",
    ) -> None:
        """Add. Args: kind, message. (hypercharge-managed)"""
        nonlocal n
        n += 1
        ends.append(
            LooseEnd(
                id=f"LE-{n:03d}",
                kind=kind,
                message=message,
                chat_id=chat_id,
                suggested=suggested or _default_suggested(kind),
                user_surface=user_surface,
                user_prompt=user_prompt or _default_user_prompt(kind, message),
            )
        )

    if not (root / ".cursor").is_dir():
        add("setup", "Hypercharge not set up in this repo.", suggested="hypercharge setup --path <repo_root>")
        return ends

    session_stale_days, graph_stale_days = _profile_thresholds(root)
    lock = load_lock(root)
    active = active_open_chats(root)
    ptr = current_chat_id(root)

    onboard_age = _onboard_age_days(root)

    if not graph_is_present(root):
        add(
            "graph",
            "Code map missing — repo claims are UNVERIFIED.",
            suggested="graphify update .",
            user_surface=False,
            user_prompt="",
        )
    else:
        last_graph_touch = lock.get("last_day_wrapup") or lock.get("last_chat_wrapup")
        age = _days_since(str(last_graph_touch)) if last_graph_touch else None
        if age is None:
            p = graph_json_path(root)
            if p.is_file():
                mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
                age = (datetime.now(timezone.utc) - mtime).days
        if age is not None and age >= graph_stale_days:
            gh = graph_hash(root) or "?"
            add(
                "graph",
                f"Code map stale ({age}d, {gh}) — refresh before architecture answers.",
                suggested="graphify update .",
            )

    last_day = lock.get("last_day_wrapup")
    last_chat = lock.get("last_chat_wrapup")
    if not last_day:
        skip_wrapup = onboard_age is not None and onboard_age < 3
        chatted_today = bool(last_chat and _days_since(str(last_chat)) == 0)
        if not skip_wrapup and not chatted_today:
            add(
                "wrapup",
                "No day wrapup on record — session may be out of date.",
                suggested="hypercharge wrapup --day",
                user_surface=False,
                user_prompt="When you finish today, say **done for the day** — I'll refresh the code map.",
            )
    else:
        day_age = _days_since(str(last_day))
        if day_age is not None and day_age >= 1:
            add(
                "wrapup",
                f"Last day wrapup was {day_age}d ago ({last_day}).",
                suggested="hypercharge wrapup --start-day review, then wrapup --day when finishing",
            )

    for chat in active:
        cid = chat.get("id", "?")
        goal = chat.get("goal", "—")
        la = chat.get("last_active", "")
        idle = _days_since(la) if la else None

        for q in chat.get("open_questions") or []:
            add(
                "open_question",
                f"[{cid}] {q}",
                chat_id=cid,
                suggested="User marks done | todo | defer — then patch OPEN_CHATS",
            )

        if chat.get("blocked_on"):
            add(
                "blocked",
                f"[{cid}] blocked: {chat['blocked_on']}",
                chat_id=cid,
                suggested="Resolve blocker or set status blocked in OPEN_CHATS",
            )

        if idle is not None and idle >= session_stale_days:
            add(
                "stale_thread",
                f"[{cid}] idle {idle}d — {goal}",
                chat_id=cid,
                suggested="Resume, archive (wrapup --archive), or mark stale",
            )
        elif idle is not None and idle >= 1 and (chat.get("open_questions") or chat.get("files_touched")):
            add(
                "open_thread",
                f"[{cid}] left open {idle}d with unfinished work — {goal}",
                chat_id=cid,
                suggested="wrap up thread or confirm still todo",
            )

    if active and not any(c.get("id") == ptr for c in active):
        add(
            "pointer",
            f"CURRENT_CHAT ({ptr}) not in OPEN_CHATS — register or pick a thread.",
            chat_id=ptr,
            suggested="hypercharge new-chat --goal \"…\" or resume existing id",
        )

    session_path = root / CURSOR_SESSION / "REPO_SESSION.md"
    if session_path.is_file():
        text = session_path.read_text(encoding="utf-8")
        initiative = _section_lines(text, "Current initiative")
        if not initiative:
            add(
                "session",
                "REPO_SESSION has no Current initiative — team focus unclear.",
                suggested="Ask user; append ## Current initiative after confirm",
                user_surface=True,
                user_prompt="What's today's focus?",
            )

    return ends


def _default_user_prompt(kind: str, message: str) -> str:
    """Internal _default_user_prompt. Args: kind, message. Returns: prompts.get(kind, ''). (hypercharge-managed)"""
    prompts = {
        "open_question": message.split("] ", 1)[-1] if "] " in message else message,
        "session": "What's today's focus?",
        "wrapup": "When you finish today, say **done for the day**.",
        "graph": "I'll refresh the code map in the background.",
        "stale_thread": "Want to pick this thread back up or close it out?",
        "open_thread": "Still working on this, or should we archive it?",
        "blocked": "What's blocking this — still stuck?",
    }
    return prompts.get(kind, "")


def _default_suggested(kind: str) -> str:
    """Internal _default_suggested. Args: kind. Returns: {'graph': 'graphify update .', 'wrapup': 'hypercha. (hypercharge-managed)"""
    return {
        "graph": "graphify update .",
        "wrapup": "hypercharge wrapup --day",
        "open_question": "Patch OPEN_CHATS after user reply",
        "stale_thread": "hypercharge wrapup --archive or resume",
        "open_thread": "hypercharge wrapup or confirm still active",
        "blocked": "Update OPEN_CHATS status / blocked_on",
        "pointer": "hypercharge new-chat or set CURRENT_CHAT to active id",
        "setup": "hypercharge setup",
        "compile": "hypercharge compile",
        "session": "Update REPO_SESSION.md Current initiative",
    }.get(kind, "Resolve with user")


def build_start_day_text(root: Path) -> str:
    """Morning briefing for agents — immersive cues, no interrogation grid."""
    root = root.resolve()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [f"# Start day — {today}", ""]

    if not (root / ".cursor").is_dir():
        lines.append("Run `hypercharge setup` first.")
        return "\n".join(lines) + "\n"

    branch = git_branch(root)
    lines.append(f"Branch: {branch}")
    lines.append("")

    session_path = root / CURSOR_SESSION / "REPO_SESSION.md"
    if session_path.is_file():
        text = session_path.read_text(encoding="utf-8")
        initiative = _section_lines(text, "Current initiative")
        if initiative:
            lines.append("## Today's focus")
            lines.extend(initiative[:5])
            lines.append("")
        decisions = _section_lines(text, "Decisions")
        if decisions:
            lines.append("## Recent decisions (context — weave into greeting)")
            lines.extend(f"- {d}" for d in decisions[:5])
            lines.append("")

    ends = collect_loose_ends(root)
    user_ends = [e for e in ends if e.user_surface and e.user_prompt]
    silent = [e for e in ends if not e.user_surface]

    if user_ends:
        lines.append("## Ask the user (one natural question — not a checklist)")
        lines.append(f"- **Primary:** {user_ends[0].user_prompt}")
        for le in user_ends[1:3]:
            lines.append(f"- Later if needed: {le.user_prompt}")
        lines.append("")

    if silent:
        lines.append("## Handle silently (do not flag as loose ends)")
        for le in silent:
            lines.append(f"- [{le.id}] {le.message}")
        lines.append("")

    blocking = [e for e in ends if e.user_surface and not e.user_prompt]
    if blocking:
        lines.append("## Needs attention")
        for le in blocking:
            lines.append(f"- {le.message}")
        lines.append("")

    active = active_open_chats(root)
    if active:
        lines.append("## Active threads")
        for chat in sorted(active, key=lambda c: c.get("last_active", ""), reverse=True):
            cid = chat.get("id", "?")
            lines.append(f"- {cid}: {chat.get('goal', '—')}")
        lines.append("")

    lines.append("## Agent presentation (mandatory)")
    lines.append("- Greet warmly; run `hypercharge wrapup --brief` for repo context — merge into one story.")
    lines.append("- Never show LE-* ids, done|todo|archive|defer grids, or internal file paths unless asked.")
    lines.append("- Call it **today's focus**, not 'Current initiative' or REPO_SESSION.")
    lines.append("- Rules compile: mention only if user asks about rules — not on start-day.")
    lines.append("- After user states focus → write ## Current initiative to REPO_SESSION.md.")
    lines.append("- Graph gaps → you run graphify; never ask the user to run it.")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_start_day_payload(root: Path) -> dict:
    """Structured start-day manifest for --json."""
    root = root.resolve()
    ends = collect_loose_ends(root)
    user_ends = [e for e in ends if e.user_surface and e.user_prompt]
    # Focus question beats stale-thread noise
    user_ends.sort(key=lambda e: (0 if e.kind == "session" else 1 if e.kind == "open_question" else 2))
    return {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "branch": git_branch(root),
        "primary_question": user_ends[0].user_prompt if user_ends else None,
        "loose_end_count": len(ends),
        "user_facing_count": len(user_ends),
        "silent_notes": [e.message for e in ends if not e.user_surface],
    }
