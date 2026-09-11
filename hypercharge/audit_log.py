"""Append-only hook audit trail for grounding and safety decisions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from hypercharge.paths import CURSOR_HYPERCHARGE

_AUDIT_NAME = "audit.jsonl"

_WRITE_TOOLS = {"Write", "StrReplace", "EditNotebook"}


def audit_log_path(root: Path) -> Path:
    """Audit log path. Args: root. Returns: root.resolve() / CURSOR_HYPERCHARGE / _AUDIT_NAME. (hypercharge-managed)"""
    return root.resolve() / CURSOR_HYPERCHARGE / _AUDIT_NAME


def append_audit(
    root: Path,
    *,
    hook: str,
    tool: str,
    decision: str,
    detail: str = "",
) -> None:
    """Append audit. Args: root. (hypercharge-managed)"""
    try:
        path = audit_log_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "hook": hook,
            "tool": tool,
            "decision": decision,
            "detail": (detail or "")[:500],
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def summarise_session(root: Path, *, chat_id: str | None = None) -> dict:
    """
    Return a summary of the current session's audit entries.
    Groups by decision type: warn, deny, allow.
    Highlights ungrounded writes (tool in Write/StrReplace/EditNotebook + decision != deny).
    Returns dict with keys: total, warns, denies, ungrounded_writes (list of {tool, path, detail, ts}).
    """
    path = audit_log_path(root)
    entries: list[dict] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    warns = sum(1 for e in entries if e.get("decision") == "warn")
    denies = sum(1 for e in entries if e.get("decision") == "deny")

    ungrounded_writes: list[dict] = []
    for e in entries:
        if (
            e.get("tool") in _WRITE_TOOLS
            and e.get("decision") in ("allow", "warn")
            and ("UNVERIFIED" in (e.get("detail") or "") or "ungrounded" in (e.get("detail") or "").lower())
        ):
            ungrounded_writes.append(
                {
                    "tool": e.get("tool", ""),
                    "path": e.get("path", ""),
                    "detail": e.get("detail", ""),
                    "ts": e.get("ts", ""),
                }
            )

    return {
        "total": len(entries),
        "warns": warns,
        "denies": denies,
        "ungrounded_writes": ungrounded_writes,
    }
