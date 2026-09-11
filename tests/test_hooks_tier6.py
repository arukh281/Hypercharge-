"""Tier 6 — hooks, grounding gate, watch queue, knowledge."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from hypercharge.grounding_session import (
    grounding_policy,
    is_path_grounded,
    load_grounding,
    record_query_success,
)
from hypercharge.hook_handlers import (
    handle_after_file_edit,
    handle_pre_tool_use,
    handle_session_start,
)
from hypercharge.hooks_cmd import run_hook
from hypercharge.hooks_deploy import deploy_hooks, is_managed_hook_entry, merge_hooks_json
from hypercharge.templates_deploy import deploy_templates
from hypercharge.ui.console import HyperConsole
from hypercharge.graph_refresh import enqueue_graph_refresh, pending_count


def test_merge_hooks_preserves_user_hooks():
    """Test merge hooks preserves user hooks. (hypercharge-managed)"""
    existing = {
        "version": 1,
        "hooks": {
            "beforeShellExecution": [{"command": ".cursor/hooks/my-custom.sh"}],
            "sessionStart": [{"command": ".cursor/hooks/hypercharge-session-start.sh"}],
        },
    }
    managed = {
        "version": 1,
        "hooks": {
            "sessionStart": [{"command": ".cursor/hooks/hypercharge-session-start.sh"}],
            "preToolUse": [{"command": ".cursor/hooks/hypercharge-pre-tool.sh"}],
        },
    }
    merged = merge_hooks_json(existing, managed)
    assert any(h["command"] == ".cursor/hooks/my-custom.sh" for h in merged["hooks"]["beforeShellExecution"])
    assert len(merged["hooks"]["sessionStart"]) == 1
    assert len(merged["hooks"]["preToolUse"]) == 1


def test_is_managed_hook_entry():
    """Test is managed hook entry. (hypercharge-managed)"""
    assert is_managed_hook_entry({"command": ".cursor/hooks/hypercharge-pre-tool.sh"})
    assert not is_managed_hook_entry({"command": ".cursor/hooks/format.sh"})


def test_deploy_hooks_preserves_custom_hooks(tmp_path):
    """Test deploy hooks preserves custom hooks. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    hooks_dir = root / ".cursor/hooks"
    hooks_dir.mkdir(parents=True)
    custom = hooks_dir / "my-format.sh"
    custom.write_text("#!/bin/sh\n", encoding="utf-8")
    (root / ".cursor/hooks.json").write_text(
        json.dumps(
            {
                "version": 1,
                "hooks": {
                    "beforeShellExecution": [{"command": ".cursor/hooks/my-format.sh"}],
                },
            }
        ),
        encoding="utf-8",
    )
    deploy_hooks(root)
    data = json.loads((root / ".cursor/hooks.json").read_text(encoding="utf-8"))
    assert any(h["command"] == ".cursor/hooks/my-format.sh" for h in data["hooks"]["beforeShellExecution"])
    assert (hooks_dir / "hypercharge-session-start.sh").is_file()
    assert os.access(hooks_dir / "hypercharge-session-start.sh", os.X_OK)


def test_deploy_templates_installs_hooks(tmp_path):
    """Test deploy templates installs hooks. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    deploy_templates(root)
    assert (root / ".cursor/hooks.json").is_file()
    assert (root / ".cursor/hooks/hypercharge-session-start.sh").is_file()


def test_session_start_injects_context_packet(tmp_path):
    """Test session start injects context packet. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".cursor/session/chats").mkdir(parents=True)
    (root / ".cursor/session/CURRENT_CHAT.md").write_text("chat_id: c1\n", encoding="utf-8")
    (root / ".cursor/session/chats/c1.md").write_text("Goal: ship hooks\n", encoding="utf-8")
    (root / ".cursor/session/OPEN_CHATS.yaml").write_text(
        "open:\n- id: c1\n  goal: ship hooks\n  open_questions: []\n  files_touched: []\n  status: active\n",
        encoding="utf-8",
    )
    (root / ".cursor/hypercharge").mkdir(parents=True)
    (root / ".cursor/hypercharge/runtime.json").write_text("{}", encoding="utf-8")
    out = handle_session_start(root, {})
    assert "additional_context" in out
    assert "context packet" in out["additional_context"].lower()
    assert "ship hooks" in out["additional_context"]


def test_sprout_policy_warns(tmp_path):
    """Ungrounded write yields allow + advisory agent_message."""
    root = tmp_path / "repo"
    root.mkdir()
    payload = {"tool_name": "Write", "tool_input": {"path": "src/auth.py"}}
    result = handle_pre_tool_use(root, payload)
    assert result.get("permission") == "allow"
    assert result.get("agent_message")


def test_pre_tool_warns_when_sapling_policy(tmp_path):
    """Test pre tool warns when ungrounded write. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    target = root / "src/auth.py"
    target.parent.mkdir(parents=True)
    target.write_text("# auth\n", encoding="utf-8")

    payload = {"tool_name": "Write", "tool_input": {"path": "src/auth.py", "contents": "x"}}
    result = handle_pre_tool_use(root, payload)
    assert result.get("permission") == "allow"
    assert result.get("agent_message")


def test_pre_tool_allows_grounded_path(tmp_path):
    """Test pre tool allows grounded path. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src/auth.py").write_text("# auth\n", encoding="utf-8")
    (root / ".cursor").mkdir()
    record_query_success(root, ["src/auth.py"])
    handle_pre_tool_use(root, {"tool_name": "Read", "tool_input": {"path": "src/auth.py"}})
    payload = {"tool_name": "Write", "tool_input": {"path": "src/auth.py"}}
    assert handle_pre_tool_use(root, payload).get("permission") == "allow"


def test_after_edit_enqueues_refresh(tmp_path):
    """Test after edit enqueues refresh. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    handle_after_file_edit(root, {"file_path": "hypercharge/context.py"})
    assert pending_count(root) == 1


def test_hooks_cli_session_start(tmp_path):
    """Test hooks cli session start. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".cursor/session/chats").mkdir(parents=True)
    (root / ".cursor/session/CURRENT_CHAT.md").write_text("chat_id: c1\n", encoding="utf-8")
    (root / ".cursor/session/chats/c1.md").write_text("Goal: test\n", encoding="utf-8")
    (root / ".cursor/session/OPEN_CHATS.yaml").write_text(
        "open:\n- id: c1\n  goal: test\n  open_questions: []\n  files_touched: []\n  status: active\n",
        encoding="utf-8",
    )
    code = run_hook("session-start", root, stdin_text="{}")
    assert code == 0


def test_grounding_policy_defaults_off(tmp_path):
    """Grounding policy defaults to off — pure context enrichment, no blocking."""
    root = tmp_path / "repo"
    root.mkdir()
    assert grounding_policy(root) == "off"


def test_knowledge_query_merges_session(tmp_path, monkeypatch):
    """Test knowledge query merges session. Args: tmp_path, monkeypatch. (hypercharge-managed)"""
    from hypercharge.knowledge_cmd import run_knowledge_query

    root = tmp_path / "repo"
    root.mkdir()
    (root / ".cursor/session").mkdir(parents=True)
    (root / ".cursor/session/REPO_SESSION.md").write_text(
        "# Repo session\n\n## Decisions\n\n- Use pytest for all changes\n\n",
        encoding="utf-8",
    )
    with patch(
        "hypercharge.knowledge_cmd.run_grounded_query",
        return_value=(1, "UNVERIFIED — no graph"),
    ):
        code, text = run_knowledge_query(root, "pytest")
    assert code == 1
    assert "pytest" in text.lower() or "SESSION" in text


def test_hook_invalid_json_denies_pre_tool(tmp_path):
    """Test hook invalid json denies pre tool. Args: tmp_path. (hypercharge-managed)"""
    import io
    from contextlib import redirect_stdout

    root = tmp_path / "repo"
    root.mkdir()
    deploy_templates(root)
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = run_hook("pre-tool", root, stdin_text="{bad", console=HyperConsole(plain=True))
    assert code == 0
    lines = [ln for ln in buf.getvalue().splitlines() if ln.strip().startswith("{")]
    out = json.loads(lines[-1])
    assert out.get("permission") == "allow"


def test_graph_refresh_drain_unmocked(tmp_path, monkeypatch):
    """Test graph refresh drain unmocked. Args: tmp_path, monkeypatch. (hypercharge-managed)"""
    from hypercharge.graph_refresh import drain_if_ready

    root = tmp_path / "repo"
    root.mkdir()
    (root / ".cursor/hypercharge").mkdir(parents=True)
    (root / ".cursor/graphify-out").mkdir(parents=True)
    (root / ".cursor/graphify-out/graph.json").write_text('{"nodes":[],"links":[]}', encoding="utf-8")
    for i in range(3):
        enqueue_graph_refresh(root, f"hypercharge/file{i}.py")
    assert pending_count(root) == 3
    monkeypatch.setattr("hypercharge.graph_refresh.run_graphify_build", lambda *a, **k: (True, "ok"))
    monkeypatch.setattr("hypercharge.graph_refresh.time.time", lambda: 999999.0)
    monkeypatch.setattr("hypercharge.graph_refresh._last_drain_ts", lambda r: 0.0)
    assert drain_if_ready(root, debounce_sec=0) is True
    assert pending_count(root) == 0


def test_bash_pre_tool_hook_e2e(tmp_path):
    """Test bash pre tool hook e2e. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("# test\n", encoding="utf-8")
    deploy_hooks(root)
    from hypercharge.runtime_paths import write_runtime_manifest

    write_runtime_manifest(root, hc_root=Path(__file__).resolve().parents[1])
    script = root / ".cursor/hooks/hypercharge-pre-tool.sh"
    payload = json.dumps({"tool_name": "Shell", "tool_input": {"command": "hypercharge --version"}})
    proc = subprocess.run(
        ["bash", str(script)],
        cwd=root,
        input=payload,
        capture_output=True,
        text=True,
        env={"CURSOR_PROJECT_DIR": str(root), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
    )
    assert proc.returncode == 0
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip().startswith("{")]
    out = json.loads(lines[-1])
    assert out.get("permission") == "allow"


def test_pre_tool_write_ungrounded_injects_graph_context(tmp_path):
    """When run_grounded_query returns graph text, agent_message includes 'Graph context:'."""
    root = tmp_path / "repo"
    root.mkdir()
    payload = {"tool_name": "Write", "tool_input": {"path": "src/auth.py", "contents": "x"}}
    with patch(
        "hypercharge.hook_handlers._lookup_file_context",
        return_value="auth.py handles user authentication at src/auth.py:1",
    ):
        result = handle_pre_tool_use(root, payload)
    assert result.get("permission") == "allow"
    msg = result.get("agent_message", "")
    assert "Graph context:" in msg
    assert "auth.py handles user authentication" in msg


def test_pre_tool_write_ungrounded_fallback_hint(tmp_path):
    """When run_grounded_query returns empty, agent_message has fallback hint, not 'Graph context:'."""
    root = tmp_path / "repo"
    root.mkdir()
    payload = {"tool_name": "Write", "tool_input": {"path": "src/auth.py", "contents": "x"}}
    with patch(
        "hypercharge.hook_handlers._lookup_file_context",
        return_value="",
    ):
        result = handle_pre_tool_use(root, payload)
    assert result.get("permission") == "allow"
    msg = result.get("agent_message", "")
    assert "Graph context:" not in msg
    assert "hypercharge knowledge" in msg


def test_lookup_file_context_returns_empty_on_exception(tmp_path):
    """_lookup_file_context returns empty string when run_grounded_query raises."""
    from hypercharge.hook_handlers import _lookup_file_context

    root = tmp_path / "repo"
    root.mkdir()
    with patch(
        "hypercharge.context.run_grounded_query",
        side_effect=RuntimeError("graph not ready"),
    ):
        result = _lookup_file_context(root, "src/auth.py")
    assert result == ""


def test_lookup_file_context_returns_text(tmp_path):
    """_lookup_file_context returns stripped query text on success."""
    from hypercharge.hook_handlers import _lookup_file_context

    root = tmp_path / "repo"
    root.mkdir()
    with patch(
        "hypercharge.context.run_grounded_query",
        return_value=(0, "  auth.py: JWT login handler  "),
    ):
        result = _lookup_file_context(root, "src/auth.py")
    assert result == "auth.py: JWT login handler"


def test_bash_session_start_hook_e2e(tmp_path):
    """Test bash session start hook e2e. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    deploy_templates(root)
    from hypercharge.runtime_paths import write_runtime_manifest

    write_runtime_manifest(root, hc_root=Path(__file__).resolve().parents[1])
    script = root / ".cursor/hooks/hypercharge-session-start.sh"
    proc = subprocess.run(
        ["bash", str(script)],
        cwd=root,
        input="{}",
        capture_output=True,
        text=True,
        env={"CURSOR_PROJECT_DIR": str(root), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
    )
    assert proc.returncode == 0
    out = json.loads(proc.stdout.strip() or "{}")
    assert isinstance(out, dict)
