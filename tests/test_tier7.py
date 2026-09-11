"""Tier 7 — runtime manifest, answer gate, auto-drain, per-turn hooks."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from hypercharge.answer_gate import assess_answer_text
from hypercharge.hook_handlers import (
    handle_after_agent_response,
    handle_after_file_edit,
    handle_before_submit_prompt,
    handle_pre_tool_use,
)
from hypercharge.graph import graphify_out_dir
from hypercharge.hooks_deploy import deploy_hooks
from hypercharge.templates_deploy import deploy_templates
from hypercharge.runtime_paths import write_runtime_manifest, resolve_hook_python
from hypercharge.graph_refresh import pending_count


def test_runtime_manifest_written(tmp_path):
    """Test runtime manifest written. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    import sys

    path = write_runtime_manifest(root, hc_root=Path(__file__).resolve().parents[1])
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["hypercharge_python"]
    assert Path(data["hypercharge_python"]).is_file()


def test_resolve_hook_python_from_runtime(tmp_path):
    """Test resolve hook python from runtime. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    import sys

    write_runtime_manifest(root, hc_root=Path(__file__).resolve().parents[1])
    py = resolve_hook_python(root)
    assert py is not None
    assert py.is_file()


def test_answer_gate_flags_untagged_claims():
    """Test answer gate flags untagged claims. (hypercharge-managed)"""
    text = (
        "The entry point is implemented in hypercharge/cli.py and handles all commands. "
        "This module is responsible for dispatching subcommands to the right handlers."
    )
    a = assess_answer_text(text)
    assert not a.ok
    assert a.claim_count >= 1


def test_answer_gate_allows_tagged():
    """Test answer gate allows tagged. (hypercharge-managed)"""
    text = (
        "GROUNDED — hypercharge/cli.py:204 dispatches commands via main(). "
        "Additional context about the repository structure."
    )
    assert assess_answer_text(text).ok


def test_answer_gate_tag_alone_fails_with_root(tmp_path):
    """Test answer gate tag alone fails with root. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "hypercharge").mkdir()
    (root / "hypercharge/cli.py").write_text("# cli\n" * 300, encoding="utf-8")
    text = (
        "GROUNDED — The entry point is implemented in hypercharge/cli.py and handles all commands."
    )
    assert not assess_answer_text(text, root).ok


def test_answer_gate_passes_with_grounded_citation(tmp_path):
    """Test answer gate passes with grounded citation. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "hypercharge").mkdir()
    (root / "hypercharge/cli.py").write_text("# cli\n" * 300, encoding="utf-8")
    from hypercharge.grounding_session import record_query_success

    record_query_success(root, ["hypercharge/cli.py"])
    text = "The entry point is in hypercharge/cli.py:1. [GROUNDED]"
    assert assess_answer_text(text, root).ok


def test_after_response_warns_not_blocks(tmp_path):
    """Default off — no advisory for ungrounded reply, never blocks."""
    root = tmp_path / "repo"
    root.mkdir()
    out = handle_after_agent_response(
        root,
        {
            "text": (
                "The code in hypercharge/context.py handles grounded queries and "
                "is responsible for validating citations on disk."
            )
        },
    )
    assert "followup_message" not in out
    assert "decision" not in out


def test_before_prompt_injects_grounding(tmp_path):
    """Test before prompt injects grounding. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".cursor/session/chats").mkdir(parents=True)
    (root / ".cursor/session/CURRENT_CHAT.md").write_text("chat_id: c1\n", encoding="utf-8")
    (root / ".cursor/session/chats/c1.md").write_text("Goal: test\n", encoding="utf-8")
    (root / ".cursor/session/OPEN_CHATS.yaml").write_text(
        "open:\n- id: c1\n  goal: test hooks\n  open_questions: []\n  files_touched: []\n  status: active\n",
        encoding="utf-8",
    )
    (root / ".cursor/session/REPO_SESSION.md").write_text(
        "# Repo session\n\n## Decisions\n\nUse knowledge CLI.\n",
        encoding="utf-8",
    )
    (root / ".cursor/hypercharge").mkdir(parents=True)
    (root / ".cursor/hypercharge/runtime.json").write_text("{}", encoding="utf-8")
    with patch("hypercharge.hook_handlers.build_prompt_grounding_digest", return_value="## Prompt grounding\n- session hit"):
        out = handle_before_submit_prompt(root, {"prompt": "where is the knowledge command?"})
    assert "prompt-grounding" in out["additional_context"]
    assert "session hit" in out["additional_context"]


def test_read_tool_records_grounded_path(tmp_path):
    """Test read tool records grounded path. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src/foo.py").write_text("# foo\n", encoding="utf-8")
    from hypercharge.grounding_session import is_path_grounded, record_query_success

    record_query_success(root, ["src/foo.py"])
    result = handle_pre_tool_use(
        root,
        {"tool_name": "Read", "tool_input": {"path": "src/foo.py"}},
    )
    assert result.get("permission") == "allow"
    assert is_path_grounded(root, "src/foo.py")


def test_before_prompt_uses_delta(tmp_path):
    """Test before prompt uses delta. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".cursor/session/chats").mkdir(parents=True)
    (root / ".cursor/session/CURRENT_CHAT.md").write_text("chat_id: c1\n", encoding="utf-8")
    (root / ".cursor/session/chats/c1.md").write_text("Goal: test\n", encoding="utf-8")
    (root / ".cursor/session/OPEN_CHATS.yaml").write_text(
        "open:\n- id: c1\n  goal: test\n  open_questions: []\n  files_touched: []\n  status: active\n",
        encoding="utf-8",
    )
    (root / ".cursor/hypercharge").mkdir(parents=True)
    (root / ".cursor/hypercharge/runtime.json").write_text("{}", encoding="utf-8")
    out = handle_before_submit_prompt(root, {})
    assert "turn-delta" in out["additional_context"]
    assert "turn delta" in out["additional_context"].lower()


def test_after_edit_enqueues_without_sync_build(tmp_path):
    """After-edit queues a graph refresh but never builds synchronously in-hook."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".cursor").mkdir()
    gdir = graphify_out_dir(root)
    gdir.mkdir(parents=True, exist_ok=True)
    (gdir / "graph.json").write_text('{"nodes":[],"links":[]}', encoding="utf-8")

    from hypercharge.graph_refresh import pending_count

    handle_after_file_edit(root, {"file_path": "a.py"})
    handle_after_file_edit(root, {"file_path": "b.py"})
    handle_after_file_edit(root, {"file_path": "c.py"})
    assert pending_count(root) == 3


def test_setup_doctor_hooks_tier(tmp_path):
    """Test setup doctor hooks tier. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    deploy_templates(root)
    deploy_hooks(root)
    from hypercharge.runtime_paths import write_runtime_manifest
    from hypercharge.doctor_cmd import build_doctor_report, _doctor_exit_code

    write_runtime_manifest(root)
    from hypercharge.memory_index import rebuild_memory_index

    rebuild_memory_index(root)
    report = build_doctor_report(root)
    assert "runtime_json_missing" not in report.get("hooks_issues", [])
    assert _doctor_exit_code(report, tier="hooks") == 0
    assert _doctor_exit_code(report, tier="ready") == 0


def test_doctor_ready_fails_without_runtime(tmp_path):
    """Test doctor ready fails without runtime. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    deploy_templates(root)
    deploy_hooks(root)
    from hypercharge.doctor_cmd import build_doctor_report, _doctor_exit_code

    report = build_doctor_report(root)
    assert "runtime_json_missing" in report.get("hooks_issues", [])
    assert _doctor_exit_code(report, tier="ready") == 1


def test_after_edit_auto_logs_file(tmp_path):
    """Test after edit auto logs file. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".cursor/session/chats").mkdir(parents=True)
    (root / ".cursor/session/CURRENT_CHAT.md").write_text("chat_id: c1\n", encoding="utf-8")
    (root / ".cursor/session/chats/c1.md").write_text("# chat\n", encoding="utf-8")
    (root / ".cursor/session/OPEN_CHATS.yaml").write_text(
        "open:\n- id: c1\n  goal: test\n  open_questions: []\n  files_touched: []\n  status: active\n",
        encoding="utf-8",
    )
    handle_after_file_edit(root, {"file_path": "foo.py"})
    from hypercharge.session import get_open_chat_entry

    entry = get_open_chat_entry(root, "c1")
    assert "foo.py" in (entry.get("files_touched") or [])


def test_pre_tool_allows_ungrounded_read_in_warn(tmp_path):
    """Warn policy: ungrounded Read is allowed (no deny)."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src/secret.py").write_text("# secret\n", encoding="utf-8")
    result = handle_pre_tool_use(
        root,
        {"tool_name": "Read", "tool_input": {"path": "src/secret.py"}},
    )
    assert result.get("permission") == "allow"


def test_answer_gate_accepts_cursor_fence(tmp_path):
    """Test answer gate accepts cursor fence. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "hypercharge").mkdir()
    (root / "hypercharge/cli.py").write_text("# cli\n" * 50, encoding="utf-8")
    from hypercharge.grounding_session import record_query_success

    record_query_success(root, ["hypercharge/cli.py"])
    text = (
        "The entry point dispatches via main in ```5:10:hypercharge/cli.py``` "
        "and handles all CLI routing for the package."
    )
    assert assess_answer_text(text, root).ok


def test_turn_delta_includes_initiative(tmp_path):
    """Test turn delta includes initiative. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".cursor/session").mkdir(parents=True)
    (root / ".cursor/session/REPO_SESSION.md").write_text(
        "# Repo session\n\n## Current initiative\n\nShip Tier 7 hooks.\n\n## Decisions\n\nBlock by default.\n",
        encoding="utf-8",
    )
    from hypercharge.turn_delta import build_turn_delta

    delta = build_turn_delta(root)
    assert "initiative:" in delta
    assert "Ship Tier 7" in delta
    assert "decisions:" in delta.lower() or "Block by default" in delta


def test_knowledge_surfaces_grounded_paths(tmp_path):
    """Test knowledge surfaces grounded paths. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".cursor/hypercharge").mkdir(parents=True)
    from hypercharge.grounding_session import record_query_success
    from hypercharge.knowledge_cmd import run_knowledge_query

    record_query_success(root, ["hypercharge/cli.py"])
    with patch("hypercharge.knowledge_cmd.run_grounded_query", return_value=(1, "UNVERIFIED")):
        _, body = run_knowledge_query(root, "cli entry", budget=200)
    assert "## SESSION grounded paths" in body
    assert "hypercharge/cli.py" in body


def test_onboard_doctor_not_ready_exit(tmp_path, monkeypatch):
    """Test onboard doctor not ready exit. Args: tmp_path, monkeypatch. (hypercharge-managed)"""
    import subprocess

    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("# test\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)

    from hypercharge.onboard_cmd import run_onboard
    from hypercharge.ui.console import HyperConsole

    monkeypatch.setattr(
        "hypercharge.doctor_cmd._doctor_exit_code",
        lambda report, tier="ideal": 1,
    )
    code = run_onboard(
        root,
        HyperConsole(plain=True),
        skip_machine_install=True,
        no_graph=True,
        as_json=True,
    )
    assert code == 1


def test_onboard_json_stdout_is_json_only(tmp_path, monkeypatch, capsys):
    """Test onboard json stdout is json only. Args: tmp_path, monkeypatch, capsys. (hypercharge-managed)"""
    import subprocess

    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("# test\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)

    from hypercharge.onboard_cmd import run_onboard
    from hypercharge.ui.console import HyperConsole

    monkeypatch.setattr("hypercharge.setup_cmd.run_graphify_build", lambda *a, **k: (True, "ok"))
    code = run_onboard(
        root,
        HyperConsole(plain=True),
        skip_machine_install=True,
        no_graph=True,
        as_json=True,
    )
    assert code == 0
    out = capsys.readouterr().out.strip()
    assert out.startswith("{")
    data = json.loads(out)
    assert data.get("status") == "ready"
    assert "[" not in out.split("\n")[0]  # no step banners like [1/6]


def test_onboard_happy_path_writes_manifest(tmp_path):
    """Test onboard happy path writes manifest. Args: tmp_path. (hypercharge-managed)"""
    import subprocess

    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("# test\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)

    from hypercharge.onboard_cmd import run_onboard
    from hypercharge.ui.console import HyperConsole

    code = run_onboard(
        root,
        HyperConsole(plain=True),
        skip_machine_install=True,
        no_graph=True,
        as_json=True,
    )
    assert code == 0
    manifest = root / ".cursor/hypercharge/last-onboard.json"
    assert manifest.is_file()
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data.get("status") == "ready"
    assert "artifacts" in data


def test_profile_syncs_autonomy(tmp_path):
    """Test profile syncs autonomy. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".cursor").mkdir()
    (root / ".cursor/repo-profile.json").write_text(
        '{"graph": {"path": "graphify-out/graph.json"}}',
        encoding="utf-8",
    )
    deploy_templates(root)
    profile = json.loads((root / ".cursor/repo-profile.json").read_text(encoding="utf-8"))
    assert profile.get("autonomy", {}).get("grounding_gate") == "warn"


def test_setup_defaults_grounding_warn(tmp_path):
    """Consumer setup deploys the advisory default (warn), overriding any prior value."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".cursor").mkdir()
    (root / ".cursor/repo-profile.json").write_text(
        '{"autonomy": {"grounding_gate": "off"}}',
        encoding="utf-8",
    )
    deploy_templates(root)
    profile = json.loads((root / ".cursor/repo-profile.json").read_text(encoding="utf-8"))
    assert profile["autonomy"]["grounding_gate"] == "warn"


def test_prompt_grounding_includes_memory(tmp_path):
    """Test prompt grounding includes memory. Args: tmp_path. (hypercharge-managed)"""
    from hypercharge.hook_handlers import build_prompt_grounding_digest
    from hypercharge.memory_index import rebuild_memory_index

    root = tmp_path / "repo"
    root.mkdir()
    (root / ".cursor/session").mkdir(parents=True)
    (root / ".cursor/session/REPO_SESSION.md").write_text(
        "# Repo session\n\n## Decisions\n\nUse FTS memory for JWT middleware recall.\n",
        encoding="utf-8",
    )
    rebuild_memory_index(root)
    body = build_prompt_grounding_digest(root, "JWT middleware recall", budget=600)
    assert "MEMORY" in body or "JWT" in body or "middleware" in body


def test_deploy_hooks_includes_tier7_scripts(tmp_path):
    """Test deploy hooks includes tier7 scripts. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    deploy_hooks(root)
    hooks = root / ".cursor/hooks"
    assert (hooks / "_hypercharge-python.sh").is_file()
    assert (hooks / "hypercharge-after-response.sh").is_file()
    data = json.loads((root / ".cursor/hooks.json").read_text(encoding="utf-8"))
    assert "beforeSubmitPrompt" in data["hooks"]
    assert "afterAgentResponse" in data["hooks"]
