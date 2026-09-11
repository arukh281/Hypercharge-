"""Turn tracker + Stop-hook reminder tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

from hypercharge.hook_handlers import handle_after_agent_response, handle_after_file_edit
from hypercharge.turn_tracker import (
    AUTO_HOOK_NOTE,
    assess_turn_compliance,
    format_stop_reminder,
    is_semantic_log_note,
    load_turn_state,
    record_turn_semantic_log,
    reset_turn_state,
    save_turn_state,
)


def test_is_semantic_log_note():
    """Test is semantic log note. (hypercharge-managed)"""
    assert not is_semantic_log_note("")
    assert not is_semantic_log_note(AUTO_HOOK_NOTE)
    assert not is_semantic_log_note("auto: file edited (hook)")
    assert is_semantic_log_note("Implemented stop-hook reminder")


def test_stop_reminder_after_edit_without_semantic_log(tmp_path):
    """Test stop reminder after edit without semantic log. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "hypercharge").mkdir()
    target = root / "hypercharge/foo.py"
    target.write_text("# foo\n", encoding="utf-8")

    reset_turn_state(root)
    handle_after_file_edit(root, {"tool_input": {"path": str(target)}})

    compliance = assess_turn_compliance(root)
    assert compliance.missing_semantic_log
    reminder = format_stop_reminder(root)
    assert reminder is not None
    assert "Session log" in reminder
    assert "foo.py" in reminder


def test_stop_reminder_cleared_after_semantic_log(tmp_path):
    """Test stop reminder cleared after semantic log. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    reset_turn_state(root)
    state = load_turn_state(root)
    state["edits"] = ["hypercharge/foo.py"]
    save_turn_state(root, state)
    record_turn_semantic_log(root, note="Documented change")

    assert not assess_turn_compliance(root).missing_semantic_log
    assert format_stop_reminder(root) is None


def test_after_response_includes_stop_reminder(tmp_path):
    """Test after response includes stop reminder. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "hypercharge").mkdir()
    target = root / "hypercharge/bar.py"
    target.write_text("# bar\n", encoding="utf-8")

    reset_turn_state(root)
    handle_after_file_edit(root, {"tool_input": {"path": str(target)}})

    out = handle_after_agent_response(root, {"text": "Done."})
    assert "additional_context" in out
    assert "stop-reminder" in out["additional_context"]
    assert "Session log" in out["additional_context"]


def test_commit_reminder_when_uncommitted(tmp_path):
    """Test commit reminder when uncommitted. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    (root / "readme.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "readme.md"], cwd=root, check=True, capture_output=True)

    reset_turn_state(root)
    state = load_turn_state(root)
    state["edits"] = ["readme.md"]
    state["semantic_log"] = True
    save_turn_state(root, state)

    reminder = format_stop_reminder(root)
    assert reminder is not None
    assert "Commit policy" in reminder


def test_out_of_repo_edit_is_not_recorded(tmp_path):
    """An edit to a file outside the repo (e.g. an in-session workflow script) must not
    be counted as a repo edit — otherwise the Stop advisory fires for foreign files."""
    root = tmp_path / "repo"
    root.mkdir()
    reset_turn_state(root)

    foreign = tmp_path / "elsewhere" / "script.js"
    foreign.parent.mkdir(parents=True)
    foreign.write_text("// not in the repo\n", encoding="utf-8")
    handle_after_file_edit(root, {"tool_input": {"path": str(foreign)}})

    assert load_turn_state(root)["edits"] == []
    assert format_stop_reminder(root) is None


def test_commit_reminder_ignores_preexisting_dirty_files(tmp_path):
    """Reproduces the loop: a working tree left dirty by a pre-existing file the agent
    never touched this turn must not trigger the commit advisory."""
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    (root / "stray.zip").write_text("pre-existing junk\n", encoding="utf-8")  # dirty, untouched

    reset_turn_state(root)
    # This turn's only "edit" was outside the repo — nothing repo-side to commit.
    foreign = tmp_path / "outside.js"
    foreign.write_text("// foreign\n", encoding="utf-8")
    handle_after_file_edit(root, {"tool_input": {"path": str(foreign)}})

    assert format_stop_reminder(root) is None


def test_stop_reminder_emitted_once_per_turn(tmp_path):
    """The Stop advisory is emitted at most once per turn — a re-firing Stop hook (idle
    on a background job) must not re-nag the same unsatisfiable reminder every cycle."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "hypercharge").mkdir()
    (root / "hypercharge/foo.py").write_text("# foo\n", encoding="utf-8")

    reset_turn_state(root)
    state = load_turn_state(root)
    state["edits"] = ["hypercharge/foo.py"]
    save_turn_state(root, state)

    first = handle_after_agent_response(root, {"text": "Done."})
    assert "stop-reminder" in first.get("additional_context", "")

    second = handle_after_agent_response(root, {"text": "Still waiting on the job."})
    assert "stop-reminder" not in second.get("additional_context", "")
