"""Graph freshness — staleness detection and auto-refresh."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from hypercharge.graph_freshness import (
    graph_predates_last_commit,
    graph_stale_reason,
)
from hypercharge.hook_handlers import handle_after_agent_response, handle_pre_tool_use


def _block_profile(root: Path) -> None:
    """Internal _block_profile. Args: root. (hypercharge-managed)"""
    (root / ".cursor").mkdir(exist_ok=True)
    (root / ".cursor/repo-profile.json").write_text(
        '{"autonomy": {"grounding_gate": "block"}}',
        encoding="utf-8",
    )


def _git_commit(root: Path, filename: str, message: str) -> None:
    """Internal _git_commit. Args: root, filename, message. (hypercharge-managed)"""
    (root / filename).write_text("content\n", encoding="utf-8")
    subprocess.run(["git", "add", filename], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=root,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t.com",
        },
    )


def test_graph_predates_last_commit(tmp_path):
    """Test graph predates last commit. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    graph_dir = root / ".cursor/graphify-out"
    graph_dir.mkdir(parents=True)
    graph_path = graph_dir / "graph.json"
    graph_path.write_text('{"nodes": []}\n', encoding="utf-8")
    os.utime(graph_path, (time.time() - 3600, time.time() - 3600))
    _git_commit(root, "readme.md", "init")
    assert graph_predates_last_commit(root) is True
    assert graph_stale_reason(root) == "predates_commit"


def test_graph_stale_reason_none_when_fresh(tmp_path):
    """A graph newer than the last commit and within the age threshold is not stale."""
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    _git_commit(root, "f.md", "c")
    graph_dir = root / ".cursor/graphify-out"
    graph_dir.mkdir(parents=True)
    (graph_dir / "graph.json").write_text('{"nodes": []}\n', encoding="utf-8")
    assert graph_stale_reason(root) is None


def test_block_policy_denies_ungrounded_write(tmp_path):
    """Test block policy denies ungrounded write. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src/a.py").write_text("x = 1\n", encoding="utf-8")
    _block_profile(root)
    result = handle_pre_tool_use(
        root,
        {"tool_name": "Write", "tool_input": {"path": "src/a.py", "contents": "x = 2\n"}},
    )
    assert result.get("permission") == "deny"


def test_warn_policy_allows_ungrounded_write(tmp_path):
    """Test warn policy allows ungrounded write. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src/a.py").write_text("x = 1\n", encoding="utf-8")
    (root / ".cursor").mkdir()
    (root / ".cursor/repo-profile.json").write_text(
        '{"autonomy": {"grounding_gate": "warn"}}',
        encoding="utf-8",
    )
    result = handle_pre_tool_use(
        root,
        {"tool_name": "Write", "tool_input": {"path": "src/a.py", "contents": "x = 2\n"}},
    )
    assert result.get("permission") == "allow"
    assert result.get("agent_message")


def test_block_policy_semantic_log_reminder_not_duplicated(tmp_path):
    """The missing-session-log reminder is delivered once via additional_context, not
    also as a separate followup_message (the old code sent it twice under block)."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "hypercharge").mkdir()
    target = root / "hypercharge/foo.py"
    target.write_text("# foo\n", encoding="utf-8")
    _block_profile(root)
    from hypercharge.turn_tracker import load_turn_state, reset_turn_state, save_turn_state

    reset_turn_state(root)
    state = load_turn_state(root)
    state["edits"] = ["hypercharge/foo.py"]
    save_turn_state(root, state)

    out = handle_after_agent_response(root, {"text": "Done."})
    # Reminder is present, in additional_context, and appears exactly once.
    assert "followup_message" not in out
    ctx = out.get("additional_context", "")
    assert "Session log" in ctx
    assert ctx.count("hypercharge log") == 1


def _answer_gate_repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "hypercharge").mkdir()
    (root / "hypercharge/bar.py").write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")
    _block_profile(root)
    from hypercharge.turn_tracker import reset_turn_state

    reset_turn_state(root)
    return root


def test_answer_gate_suppressed_by_single_citation(tmp_path):
    """One on-disk-valid path:line citation suppresses the grounding advisory (S2)."""
    root = _answer_gate_repo(tmp_path)
    text = (
        "The dispatcher is implemented in `hypercharge/bar.py:2` and handles every "
        "subcommand; the function returns the parsed args and uses the config module."
    )
    out = handle_after_agent_response(root, {"text": text})
    assert "Grounding note" not in out.get("additional_context", "")


def test_answer_gate_nags_uncited_repo_claims(tmp_path):
    """A claim naming a file with no line citation still gets the advisory."""
    root = _answer_gate_repo(tmp_path)
    text = (
        "The dispatcher is implemented in hypercharge/bar.py and handles every "
        "subcommand; the function returns the parsed args and uses the config module."
    )
    out = handle_after_agent_response(root, {"text": text})
    assert "Grounding note" in out.get("additional_context", "")
