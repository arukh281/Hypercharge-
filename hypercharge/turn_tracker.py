"""Per-turn edit / log / commit tracking for Stop-hook advisories."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from hypercharge.paths import CURSOR_HYPERCHARGE

AUTO_HOOK_NOTE = "auto: file edited (hook)"
_STATE_FILE = "turn-state.json"


def _utc_now() -> str:
    """Internal _utc_now. Returns: datetime.now(timezone.utc).replace(microsecond=0).. (hypercharge-managed)"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _state_path(root: Path) -> Path:
    """Per-session turn-state file when a session id is set, else the shared file."""
    from hypercharge.session_scope import session_slug

    base = root.resolve() / CURSOR_HYPERCHARGE
    slug = session_slug()
    if slug:
        return base / "sessions" / slug / _STATE_FILE
    return base / _STATE_FILE


def _empty_state() -> dict:
    """Internal _empty_state. Returns: {'turn_started_at': _utc_now(), 'edits': [], 'sema. (hypercharge-managed)"""
    return {
        "turn_started_at": _utc_now(),
        "edits": [],
        "semantic_log": False,
        "commit_this_turn": False,
        "stop_reminded": False,
    }


def load_turn_state(root: Path) -> dict:
    """Load turn state; returns empty structure if missing."""
    path = _state_path(root)
    if not path.is_file():
        return _empty_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("edits", [])
            data.setdefault("semantic_log", False)
            data.setdefault("commit_this_turn", False)
            data.setdefault("stop_reminded", False)
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return _empty_state()


def save_turn_state(root: Path, state: dict) -> None:
    """Persist turn state atomically so a concurrent hook process in the same session
    never reads a half-written file (which load_turn_state would treat as empty)."""
    from hypercharge.paths import atomic_write_json

    try:
        atomic_write_json(_state_path(root), state)
    except OSError:
        pass


def reset_turn_state(root: Path) -> None:
    """Start a fresh turn (called on beforeSubmitPrompt)."""
    save_turn_state(root, _empty_state())


def record_turn_edit(root: Path, path: str) -> None:
    """Record a file edit during the current agent turn."""
    state = load_turn_state(root)
    norm = path.strip()
    if norm and norm not in state["edits"]:
        state["edits"].append(norm)
    save_turn_state(root, state)


def is_semantic_log_note(note: str) -> bool:
    """True when a log note counts as a human/agent summary (not hook auto-touch)."""
    text = (note or "").strip()
    if not text:
        return False
    if text == AUTO_HOOK_NOTE:
        return False
    if text.startswith("auto:"):
        return False
    return True


def record_turn_semantic_log(root: Path, *, note: str = "", decision: str = "") -> None:
    """Mark that the agent left a meaningful session note this turn."""
    if not is_semantic_log_note(note) and not (decision or "").strip():
        return
    state = load_turn_state(root)
    state["semantic_log"] = True
    save_turn_state(root, state)


def record_turn_commit(root: Path) -> None:
    """Mark that git commit ran during this turn."""
    state = load_turn_state(root)
    state["commit_this_turn"] = True
    save_turn_state(root, state)


def _git_commit_command(cmd: str) -> bool:
    """Internal _git_commit_command. Args: cmd. Returns: bool(re.search('\\bgit\\s+commit\\b', cmd or '', r. (hypercharge-managed)"""
    return bool(re.search(r"\bgit\s+commit\b", cmd or "", re.IGNORECASE))


def is_git_commit_command(cmd: str) -> bool:
    """True when a shell command is a git commit."""
    return _git_commit_command(cmd)


def _edits_uncommitted(root: Path, edits: list[str]) -> bool:
    """True when any of THIS turn's own edited paths are still uncommitted.

    Scoped to the agent's recorded edits — a working tree left dirty by pre-existing
    or unrelated files (that the agent never touched this turn) must never trigger the
    commit advisory. That whole-tree check was what made the reminder loop forever.
    """
    paths = [e for e in edits if e and not e.startswith("/")]
    if not paths:
        return False
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain", "--", *paths],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return bool(proc.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        return False


@dataclass
class TurnCompliance:
    edits: list[str]
    missing_semantic_log: bool
    missing_commit: bool


def assess_turn_compliance(root: Path) -> TurnCompliance:
    """Check whether this turn satisfied session log + commit expectations."""
    state = load_turn_state(root)
    edits = list(state.get("edits") or [])
    missing_log = bool(edits) and not bool(state.get("semantic_log"))
    missing_commit = (
        bool(edits)
        and not bool(state.get("commit_this_turn"))
        and _edits_uncommitted(root, edits)
    )
    return TurnCompliance(
        edits=edits,
        missing_semantic_log=missing_log,
        missing_commit=missing_commit,
    )


def format_stop_reminder(root: Path) -> str | None:
    """Advisory text for Stop hook when session log or commit policy may be violated."""
    compliance = assess_turn_compliance(root)
    if not compliance.edits:
        return None

    lines: list[str] = ["<!-- hypercharge-managed: stop-reminder -->"]
    if compliance.missing_semantic_log:
        sample = ", ".join(compliance.edits[:3])
        extra = f" (+{len(compliance.edits) - 3} more)" if len(compliance.edits) > 3 else ""
        lines.append(
            "**Session log:** You edited files this turn but did not leave a semantic note. "
            f"Before finishing, run `hypercharge log --file <path> --note \"…\"` "
            f"(edited: {sample}{extra}). Hook auto-logs do not count."
        )
    if compliance.missing_commit:
        lines.append(
            "**Commit policy:** Uncommitted changes remain after edits this turn. "
            "During plan execution, commit locally when the batch is complete; "
            "never `git push` without explicit user approval."
        )
    if len(lines) == 1:
        return None
    return "\n".join(lines)
