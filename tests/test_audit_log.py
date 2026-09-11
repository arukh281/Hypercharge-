"""Tests for audit_log.summarise_session."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypercharge.audit_log import summarise_session
from hypercharge.paths import CURSOR_HYPERCHARGE


def _write_audit(root: Path, entries: list[dict]) -> None:
    """Internal _write_audit. Args: root, entries. (hypercharge-managed)"""
    audit_dir = root / CURSOR_HYPERCHARGE
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_file = audit_dir / "audit.jsonl"
    with audit_file.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry) + "\n")


def test_summarise_session_counts(tmp_path):
    """Test summarise session counts. Args: tmp_path. (hypercharge-managed)"""
    entries = [
        {"ts": "2026-06-17T07:00:00Z", "hook": "pre-tool", "tool": "Read", "decision": "allow", "detail": ""},
        {"ts": "2026-06-17T07:01:00Z", "hook": "pre-tool", "tool": "Shell", "decision": "warn", "detail": "unsafe shell"},
        {"ts": "2026-06-17T07:02:00Z", "hook": "pre-tool", "tool": "Shell", "decision": "deny", "detail": "blocked"},
        {"ts": "2026-06-17T07:03:00Z", "hook": "pre-tool", "tool": "Write", "decision": "warn", "detail": "UNVERIFIED claim"},
        {"ts": "2026-06-17T07:04:00Z", "hook": "pre-tool", "tool": "StrReplace", "decision": "deny", "detail": "ungrounded edit"},
    ]
    _write_audit(tmp_path, entries)

    result = summarise_session(tmp_path)

    assert result["total"] == 5
    assert result["warns"] == 2
    assert result["denies"] == 2


def test_summarise_session_ungrounded_write_detected(tmp_path):
    """Test summarise session ungrounded write detected. Args: tmp_path. (hypercharge-managed)"""
    entries = [
        {"ts": "2026-06-17T08:00:00Z", "hook": "pre-tool", "tool": "Write", "decision": "allow", "detail": "UNVERIFIED"},
        {"ts": "2026-06-17T08:01:00Z", "hook": "pre-tool", "tool": "StrReplace", "decision": "warn", "detail": "ungrounded change to foo.py"},
        # This one is denied — should NOT appear in ungrounded_writes
        {"ts": "2026-06-17T08:02:00Z", "hook": "pre-tool", "tool": "Write", "decision": "deny", "detail": "UNVERIFIED"},
        # Write that is grounded — should NOT appear
        {"ts": "2026-06-17T08:03:00Z", "hook": "pre-tool", "tool": "Write", "decision": "allow", "detail": "GROUNDED"},
        # EditNotebook ungrounded
        {"ts": "2026-06-17T08:04:00Z", "hook": "pre-tool", "tool": "EditNotebook", "decision": "allow", "detail": "UNVERIFIED notebook edit"},
    ]
    _write_audit(tmp_path, entries)

    result = summarise_session(tmp_path)

    uw = result["ungrounded_writes"]
    assert len(uw) == 3, f"expected 3 ungrounded writes, got {len(uw)}: {uw}"

    tools = {e["tool"] for e in uw}
    assert "Write" in tools
    assert "StrReplace" in tools
    assert "EditNotebook" in tools

    # Denied Write must not appear
    for entry in uw:
        assert entry.get("tool") != "Write" or "GROUNDED" not in entry.get("detail", "")


def test_summarise_session_no_ungrounded_writes(tmp_path):
    """Test summarise session no ungrounded writes. Args: tmp_path. (hypercharge-managed)"""
    entries = [
        {"ts": "2026-06-17T09:00:00Z", "hook": "pre-tool", "tool": "Write", "decision": "allow", "detail": "GROUNDED"},
        {"ts": "2026-06-17T09:01:00Z", "hook": "pre-tool", "tool": "Read", "decision": "allow", "detail": ""},
    ]
    _write_audit(tmp_path, entries)

    result = summarise_session(tmp_path)

    assert result["ungrounded_writes"] == []


def test_summarise_session_missing_file(tmp_path):
    """Test summarise session missing file. Args: tmp_path. (hypercharge-managed)"""
    result = summarise_session(tmp_path)

    assert result["total"] == 0
    assert result["warns"] == 0
    assert result["denies"] == 0
    assert result["ungrounded_writes"] == []
