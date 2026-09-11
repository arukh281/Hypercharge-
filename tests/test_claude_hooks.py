"""Claude Code hook adapter and deploy tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from hypercharge.claude_hook_adapter import (
    claude_payload_to_handler,
    handler_result_to_claude,
    run_claude_hook,
)
from hypercharge.claude_hooks_deploy import (
    is_managed_claude_hook_entry,
    merge_claude_settings,
)
from hypercharge.grounding_session import record_query_success
from hypercharge.hooks_cmd import run_hook
from hypercharge.templates_deploy import deploy_templates


def test_claude_tool_mapping_pre_tool():
    """Test claude tool mapping pre tool. (hypercharge-managed)"""
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "hypercharge --version"},
    }
    mapped = claude_payload_to_handler("pre-tool", payload)
    assert mapped["tool_name"] == "Shell"
    assert mapped["tool_input"]["command"] == "hypercharge --version"


def test_claude_post_tool_maps_write_edit():
    """Test claude post tool maps write edit. (hypercharge-managed)"""
    write = claude_payload_to_handler(
        "after-edit",
        {"tool_name": "Write", "tool_input": {"file_path": "src/a.py"}},
    )
    assert write["file_path"] == "src/a.py"
    assert claude_payload_to_handler("after-edit", {"tool_name": "Read", "tool_input": {}}) == {}


def test_claude_pre_tool_advisory_output():
    """Pre-tool advisory injects context but never emits a permission decision."""
    out = handler_result_to_claude(
        "pre-tool",
        {"permission": "allow", "agent_message": "UNVERIFIED read"},
    )
    assert "permissionDecision" not in out["hookSpecificOutput"]
    assert "UNVERIFIED" in out["hookSpecificOutput"]["additionalContext"]


def test_claude_pre_tool_deny_never_emits_permission_decision():
    """A block-policy deny result is neutralised to advisory context in the Claude
    dialect — it must never become a permissionDecision that overrides Claude Code's
    own prompt (in either direction)."""
    out = handler_result_to_claude(
        "pre-tool",
        {"permission": "deny", "agent_message": "ungrounded write to src/app.py"},
    )
    hso = out.get("hookSpecificOutput", {})
    assert "permissionDecision" not in hso
    assert "ungrounded write" in hso.get("additionalContext", "")


def _fake_python_env(tmp_path):
    """PATH shadowed with python shims that fail the `-m hypercharge --version` check,
    so the deployed hook scripts hit their no-runtime branch."""
    import stat

    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    for name in ("python3", "python"):
        p = fakebin / name
        p.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    env = dict(os.environ)
    env["PATH"] = f"{fakebin}:{env.get('PATH', '')}"
    return env


def test_claude_pre_tool_hook_fails_open_without_runtime(tmp_path):
    """No resolvable python -> deployed pre-tool hook emits {} (fail-open), never a
    permissionDecision:deny that would brick every tool call in the repo."""
    from hypercharge.claude_hooks_deploy import deploy_claude_hooks

    root = tmp_path / "repo"
    root.mkdir()
    deploy_claude_hooks(root)
    script = root / ".claude/hooks/hypercharge-pre-tool.sh"
    payload = json.dumps(
        {"cwd": str(root), "tool_name": "Read", "tool_input": {"file_path": "x.py"}}
    )
    proc = subprocess.run(
        ["bash", str(script)],
        input=payload,
        capture_output=True,
        text=True,
        env=_fake_python_env(tmp_path),
        cwd=str(root),
    )
    out = proc.stdout.strip()
    assert out in ("{}", "")
    assert "permissionDecision" not in out
    assert "deny" not in out


def test_claude_after_response_hook_fails_open_without_runtime(tmp_path):
    """No resolvable python -> deployed Stop hook emits {} (fail-open), never a
    decision:block that would force the agent to continue every turn."""
    from hypercharge.claude_hooks_deploy import deploy_claude_hooks

    root = tmp_path / "repo"
    root.mkdir()
    deploy_claude_hooks(root)
    script = root / ".claude/hooks/hypercharge-after-response.sh"
    payload = json.dumps({"cwd": str(root), "last_assistant_message": "done"})
    proc = subprocess.run(
        ["bash", str(script)],
        input=payload,
        capture_output=True,
        text=True,
        env=_fake_python_env(tmp_path),
        cwd=str(root),
    )
    out = proc.stdout.strip()
    assert out in ("{}", "")
    assert "block" not in out


def test_claude_stop_blocks_ungrounded_answer():
    """Test claude stop blocks ungrounded answer. (hypercharge-managed)"""
    out = handler_result_to_claude(
        "after-response",
        {
            "additional_context": "Response advisory until grounded.",
            "followup_message": "Add path:line citations.",
        },
    )
    assert "hookSpecificOutput" in out
    assert "path:line" in out["hookSpecificOutput"]["additionalContext"]


def test_merge_claude_settings_preserves_user_hooks():
    """Test merge claude settings preserves user hooks. (hypercharge-managed)"""
    existing = {
        "hooks": {
            "Notification": [{"hooks": [{"type": "command", "command": ".claude/hooks/notify.sh"}]}],
            "PreToolUse": [
                {
                    "hooks": [
                        {"type": "command", "command": ".claude/hooks/hypercharge-pre-tool.sh"}
                    ]
                }
            ],
        }
    }
    managed = {
        "hooks": {
            "PreToolUse": [
                {
                    "hooks": [
                        {"type": "command", "command": ".claude/hooks/hypercharge-pre-tool.sh"}
                    ]
                }
            ],
            "Stop": [
                {
                    "hooks": [
                        {"type": "command", "command": ".claude/hooks/hypercharge-after-response.sh"}
                    ]
                }
            ],
        }
    }
    merged = merge_claude_settings(existing, managed)
    assert any(
        h["command"] == ".claude/hooks/notify.sh"
        for h in merged["hooks"]["Notification"][0]["hooks"]
    )
    assert "Stop" in merged["hooks"]


def test_is_managed_claude_hook_entry():
    """Test is managed claude hook entry. (hypercharge-managed)"""
    assert is_managed_claude_hook_entry(
        {"hooks": [{"command": ".claude/hooks/hypercharge-pre-tool.sh"}]}
    )
    assert not is_managed_claude_hook_entry(
        {"hooks": [{"command": ".claude/hooks/custom.sh"}]}
    )


def test_deploy_claude_hooks_and_templates(tmp_path):
    """Test deploy claude hooks and templates. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    deploy_templates(root)
    assert (root / ".claude/settings.json").is_file()
    assert (root / ".claude/hooks/hypercharge-pre-tool.sh").is_file()
    settings = json.loads((root / ".claude/settings.json").read_text(encoding="utf-8"))
    assert "SessionStart" in settings["hooks"]
    assert "Stop" in settings["hooks"]


def test_claude_hooks_cli_pre_tool_grounded(tmp_path):
    """Test claude hooks cli pre tool grounded. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".cursor").mkdir()
    record_query_success(root, ["src/auth.py"])
    payload = json.dumps(
        {
            "cwd": str(root),
            "tool_name": "Write",
            "tool_input": {"file_path": "src/auth.py"},
        }
    )
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        run_hook("pre-tool", root, stdin_text=payload, hook_format="claude")
    out = json.loads(buf.getvalue().strip())
    assert out == {} or "permissionDecision" not in out.get("hookSpecificOutput", {})


def test_claude_hooks_cli_invalid_json_advises(tmp_path):
    """Invalid JSON in claude format yields advisory context — never a permission decision."""
    root = tmp_path / "repo"
    root.mkdir()
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        run_hook("pre-tool", root, stdin_text="{bad", hook_format="claude")
    out = json.loads(buf.getvalue().strip())
    assert "permissionDecision" not in out["hookSpecificOutput"]
    assert out["hookSpecificOutput"]["additionalContext"]


def test_claude_bash_hook_e2e(tmp_path):
    """Test claude bash hook e2e. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("# test\n", encoding="utf-8")
    deploy_templates(root)
    from hypercharge.runtime_paths import write_runtime_manifest

    write_runtime_manifest(root, hc_root=Path(__file__).resolve().parents[1])
    script = root / ".claude/hooks/hypercharge-pre-tool.sh"
    payload = json.dumps(
        {
            "cwd": str(root),
            "tool_name": "Bash",
            "tool_input": {"command": "hypercharge --version"},
        }
    )
    proc = subprocess.run(
        ["bash", str(script)],
        cwd=root,
        input=payload,
        capture_output=True,
        text=True,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
    )
    assert proc.returncode == 0
    out = json.loads(proc.stdout.strip() or "{}")
    assert out == {} or "permissionDecision" not in out.get("hookSpecificOutput", {})


def test_run_claude_hook_stop_with_message(tmp_path):
    """After-response context surfaces as additionalContext — never as a block decision."""
    root = tmp_path / "repo"
    root.mkdir()
    with patch(
        "hypercharge.claude_hook_adapter.dispatch_hook",
        return_value={
            "additional_context": "missing tags",
            "followup_message": "fix citations",
        },
    ):
        out = run_claude_hook(
            "after-response",
            root,
            {"last_assistant_message": "The auth module lives in src/auth.py"},
        )
    assert "hookSpecificOutput" in out
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "missing tags" in ctx or "fix citations" in ctx
