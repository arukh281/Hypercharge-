"""Manager gates — read-before-write, verify, status, plan, docstrings."""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypercharge.docstrings_sync import sync_docstrings
from hypercharge.grounding_session import record_query_success
from hypercharge.hook_handlers import handle_pre_tool_use
from hypercharge.read_tracker import record_read_snapshot
from hypercharge.status_cmd import build_status_report
from hypercharge.test_oracle import claims_fixed_while_tests_red, record_test_result
from hypercharge.verify_cmd import verify_claim


def test_read_before_write_warns_without_read(tmp_path):
    """Default warn policy: write without prior read yields allow + advisory agent_message."""
    root = tmp_path
    (root / "src").mkdir()
    (root / "src/a.py").write_text("x = 1\n", encoding="utf-8")
    (root / ".cursor").mkdir()
    record_query_success(root, ["src/a.py"])
    result = handle_pre_tool_use(
        root,
        {"tool_name": "Write", "tool_input": {"path": "src/a.py", "contents": "x = 2\n"}},
    )
    assert result.get("permission") == "allow"
    assert result.get("agent_message")


def test_read_before_write_allows_after_read(tmp_path):
    """Test read before write allows after read. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path
    (root / "src").mkdir()
    (root / "src/a.py").write_text("x = 1\n", encoding="utf-8")
    (root / ".cursor").mkdir()
    record_query_success(root, ["src/a.py"])
    handle_pre_tool_use(root, {"tool_name": "Read", "tool_input": {"path": "src/a.py"}})
    result = handle_pre_tool_use(
        root,
        {"tool_name": "Write", "tool_input": {"path": "src/a.py", "contents": "x = 2\n"}},
    )
    assert result.get("permission") == "allow"


def test_verify_claim_matches_evidence(tmp_path):
    """Test verify claim matches evidence. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path
    (root / "auth.py").write_text("def login(user, password):\n    return validate_jwt(user)\n", encoding="utf-8")
    ok, _ = verify_claim(root, "login validates jwt", "auth.py:2")
    assert ok


def test_status_report_shape(tmp_path):
    """Test status report shape. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path
    (root / ".cursor").mkdir()
    report = build_status_report(root)
    assert "branch" in report
    assert "loose_ends" in report


def test_docstrings_sync_adds_missing(tmp_path):
    """Test docstrings sync adds missing. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path
    (root / ".cursor/hypercharge").mkdir(parents=True)
    (root / "m.py").write_text("def hello_world(name):\n    return name\n", encoding="utf-8")
    n, _ = sync_docstrings(root, "m.py")
    assert n >= 1
    text = (root / "m.py").read_text(encoding="utf-8")
    assert '"""' in text
    assert "hypercharge-managed" in text


def test_test_oracle_blocks_fixed_claim(tmp_path):
    """Test test oracle blocks fixed claim. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path
    (root / ".cursor/hypercharge").mkdir(parents=True)
    record_test_result(root, cmd="pytest", exit_code=1)
    assert claims_fixed_while_tests_red("This is fixed now, all tests pass.", root)
