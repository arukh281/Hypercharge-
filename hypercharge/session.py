"""Session files, open chats, lock file."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from hypercharge.paths import CURSOR_SESSION, git_branch, sanitise_branch


def _utc_now() -> str:
    """Internal _utc_now. Returns: datetime.now(timezone.utc).replace(microsecond=0).. (hypercharge-managed)"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _today() -> str:
    """Internal _today. Returns: datetime.now(timezone.utc).strftime('%Y-%m-%d'). (hypercharge-managed)"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def ensure_session_layout(root: Path) -> None:
    """Ensure session layout. Args: root. (hypercharge-managed)"""
    for sub in ("chats", "archive", "branches"):
        (root / CURSOR_SESSION / sub).mkdir(parents=True, exist_ok=True)
    (root / ".cursor/hypercharge").mkdir(parents=True, exist_ok=True)


def peek_current_chat_id(root: Path) -> str | None:
    """Return active chat id without creating one."""
    ptr = root / CURSOR_SESSION / "CURRENT_CHAT.md"
    if ptr.is_file():
        for line in ptr.read_text(encoding="utf-8").splitlines():
            if line.startswith("chat_id:"):
                return line.split(":", 1)[1].strip()
    return None


def current_chat_id(root: Path, *, create: bool = True) -> str | None:
    """Return chat id; optionally create a new thread if pointer is missing."""
    existing = peek_current_chat_id(root)
    if existing:
        return existing
    if create:
        return new_chat_id(root)
    return None


def get_open_chat_entry(root: Path, chat_id: str) -> dict:
    """Return OPEN_CHATS row for chat_id, or empty dict."""
    for item in load_open_chats(root).get("open", []):
        if item.get("id") == chat_id:
            return dict(item)
    return {}


def new_chat_id(root: Path) -> str:
    """New chat id. Args: root. Returns: cid. (hypercharge-managed)"""
    ensure_session_layout(root)
    slug = _today().replace("-", "")
    cid = f"chat_{slug}_{uuid.uuid4().hex[:8]}"
    set_current_chat(root, cid)
    chat_path = root / CURSOR_SESSION / "chats" / f"{cid}.md"
    if not chat_path.is_file():
        chat_path.write_text(
            f"# Chat {cid}\n\nStarted: {_utc_now()}\n\n",
            encoding="utf-8",
        )
    return cid


def set_current_chat(root: Path, chat_id: str) -> None:
    """Set current chat. Args: root, chat_id. (hypercharge-managed)"""
    ptr = root / CURSOR_SESSION / "CURRENT_CHAT.md"
    ptr.parent.mkdir(parents=True, exist_ok=True)
    ptr.write_text(
        f"chat_id: {chat_id}\n\nSee `.cursor/session/chats/{chat_id}.md`\n",
        encoding="utf-8",
    )


def load_open_chats(root: Path) -> dict:
    """Load open chats. Args: root. Returns: {'open': []}. (hypercharge-managed)"""
    p = root / CURSOR_SESSION / "OPEN_CHATS.yaml"
    if p.is_file():
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    return {"open": []}


def save_open_chats(root: Path, data: dict) -> None:
    """Save open chats. Args: root, data. (hypercharge-managed)"""
    p = root / CURSOR_SESSION / "OPEN_CHATS.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".yaml.tmp")
    tmp.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True), encoding="utf-8")
    tmp.replace(p)


def upsert_open_chat(root: Path, entry: dict) -> None:
    """Upsert open chat. Args: root, entry. (hypercharge-managed)"""
    data = load_open_chats(root)
    open_list = data.setdefault("open", [])
    cid = entry["id"]
    for i, item in enumerate(open_list):
        if item.get("id") == cid:
            open_list[i] = {**item, **entry, "last_active": _utc_now()}
            save_open_chats(root, data)
            return
    entry.setdefault("started", _utc_now())
    entry.setdefault("last_active", _utc_now())
    open_list.append(entry)
    save_open_chats(root, data)


def load_lock(root: Path) -> dict:
    """Load lock. Args: root. Returns: {}. (hypercharge-managed)"""
    p = root / ".cursor/hypercharge.lock"
    if p.is_file():
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return {}


def save_lock(root: Path, lock: dict) -> None:
    """Save lock. Args: root, lock. (hypercharge-managed)"""
    from hypercharge import __version__

    p = root / ".cursor/hypercharge.lock"
    p.parent.mkdir(parents=True, exist_ok=True)
    lock.setdefault("hypercharge_version", __version__)
    lock.setdefault("schema_version", 1)
    tmp = p.with_suffix(".lock.tmp")
    tmp.write_text(yaml.dump(lock, default_flow_style=False), encoding="utf-8")
    tmp.replace(p)


def append_repo_session(root: Path, line: str, branch: str | None = None, experiment: bool = False) -> None:
    """Append to ## Activity (operational roll-ups). Prefer append_decision for decisions."""
    append_session_section(root, "Activity", line, branch=branch, experiment=experiment)


def append_decision(root: Path, line: str, branch: str | None = None, experiment: bool = False) -> None:
    """Append user-confirmed decision under ## Decisions with a date stamp."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stamped = f"[{today}] {line.strip()}"
    append_session_section(root, "Decisions", stamped, branch=branch, experiment=experiment)
    if experiment:
        return
    try:
        from hypercharge.memory_index import append_memory_chunk

        append_memory_chunk(root, "decision", ".cursor/session/REPO_SESSION.md", line.strip())
    except OSError:
        pass


def supersede_decision(root: Path, needle: str) -> bool:
    """Mark matching ## Decisions lines as superseded. Returns True if any line was changed."""
    session_path = root / CURSOR_SESSION / "REPO_SESSION.md"
    if not session_path.is_file():
        return False
    text = session_path.read_text(encoding="utf-8")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    needle_lower = needle.strip().lower()
    lines = text.splitlines()
    changed = False
    in_decisions = False
    new_lines: list[str] = []
    for ln in lines:
        if ln.startswith("## "):
            in_decisions = ln[3:].strip().lower() == "decisions"
        if in_decisions and needle_lower and needle_lower in ln.lower():
            if "[SUPERSEDED" not in ln:
                ln = ln.rstrip() + f"  [SUPERSEDED {today}]"
                changed = True
        new_lines.append(ln)
    if changed:
        session_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return changed


def append_session_section(
    root: Path,
    section: str,
    line: str,
    *,
    branch: str | None = None,
    experiment: bool = False,
) -> None:
    """Append session section. Args: root, section, line. (hypercharge-managed)"""
    if experiment:
        bdir = root / CURSOR_SESSION / "branches" / sanitise_branch(branch or git_branch(root))
        bdir.mkdir(parents=True, exist_ok=True)
        target = bdir / "REPO_SESSION.md"
    else:
        target = root / CURSOR_SESSION / "REPO_SESSION.md"
    if not target.is_file():
        target.write_text(
            "# Repo session\n\nStable cross-chat decisions only.\n\n## Decisions\n\n## Activity\n\n",
            encoding="utf-8",
        )
    text = target.read_text(encoding="utf-8")
    stamp = f"- {_utc_now()}: {line.strip()}"
    if stamp in text:
        return
    heading = f"## {section}"
    if heading in text:
        parts = text.split(heading, 1)
        before = parts[0]
        after = parts[1]
        next_heading = after.find("\n## ")
        if next_heading == -1:
            body, tail = after, ""
        else:
            body, tail = after[:next_heading], after[next_heading:]
        new_body = body.rstrip() + "\n" + stamp + "\n"
        target.write_text(before + heading + new_body + tail, encoding="utf-8")
    else:
        with target.open("a", encoding="utf-8") as f:
            f.write(f"\n{heading}\n{stamp}\n")


def write_chat_wrapup_summary(root: Path, chat_id: str, body: str) -> Path:
    """Write chat wrapup summary. Args: root, chat_id, body. Returns: out. (hypercharge-managed)"""
    out = root / CURSOR_SESSION / "archive" / f"{chat_id}-wrapup.md"
    out.write_text(body, encoding="utf-8")
    return out


def write_day_wrapup_summary(root: Path, body: str) -> Path:
    """Write day wrapup summary. Args: root, body. Returns: out. (hypercharge-managed)"""
    out = root / CURSOR_SESSION / "LAST_DAY_WRAPUP.md"
    out.write_text(body, encoding="utf-8")
    return out


def chats_active_today(root: Path) -> list[dict]:
    """Chats active today. Args: root. Returns: result. (hypercharge-managed)"""
    data = load_open_chats(root)
    today = _today()
    result = []
    for item in data.get("open", []):
        la = item.get("last_active", "")
        if la.startswith(today):
            result.append(item)
    return result


def load_repo_profile_json(root: Path) -> dict:
    """Load repo profile json. Args: root. Returns: {}. (hypercharge-managed)"""
    p = root / ".cursor/repo-profile.json"
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def active_open_chats(root: Path) -> list[dict]:
    """Active open chats. Args: root. Returns: [c for c in data.get('open', []) if c.get('status'. (hypercharge-managed)"""
    data = load_open_chats(root)
    return [c for c in data.get("open", []) if c.get("status", "active") != "archived"]


def files_touched_by_chat(chat: dict) -> set[str]:
    """Files touched by chat. Args: chat. Returns: {str(f) for f in chat.get('files_touched') or [] i. (hypercharge-managed)"""
    return {str(f) for f in (chat.get("files_touched") or []) if f}


def file_overlap(chat_a: dict, chat_b: dict) -> list[str]:
    """File overlap. Args: chat_a, chat_b. Returns: sorted(a & b). (hypercharge-managed)"""
    a = files_touched_by_chat(chat_a)
    b = files_touched_by_chat(chat_b)
    return sorted(a & b)


def register_new_chat(
    root: Path,
    *,
    goal: str,
    related_to: list[str] | None = None,
) -> str:
    """Create an isolated thread and register it in OPEN_CHATS."""
    cid = new_chat_id(root)
    chat_path = root / CURSOR_SESSION / "chats" / f"{cid}.md"
    body = f"# Chat {cid}\n\nStarted: {_utc_now()}\nGoal: {goal.strip()}\n\n"
    chat_path.write_text(body, encoding="utf-8")
    entry: dict = {
        "id": cid,
        "branch": git_branch(root),
        "goal": goal.strip(),
        "open_questions": [],
        "status": "active",
        "files_touched": [],
    }
    if related_to:
        entry["related_to"] = related_to
    upsert_open_chat(root, entry)
    return cid
