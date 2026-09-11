"""Tests for the Hypercharge MCP server."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from hypercharge.mcp_server import (
    TOOL_DEFINITIONS,
    _format_memory_text,
    _format_query_text,
    handle_request,
)


# ---------------------------------------------------------------------------
# initialize
# ---------------------------------------------------------------------------


def test_initialize_returns_protocol_version():
    """Test initialize returns protocol version. (hypercharge-managed)"""
    req = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    resp = handle_request(req, Path("/tmp"))
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 1
    result = resp["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert result["serverInfo"]["name"] == "hypercharge"
    assert "tools" in result["capabilities"]


# ---------------------------------------------------------------------------
# tools/list
# ---------------------------------------------------------------------------


def test_tools_list_returns_all_tools():
    """Test tools list returns all registered tools. (hypercharge-managed)"""
    req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    resp = handle_request(req, Path("/tmp"))
    assert resp["id"] == 2
    names = {t["name"] for t in resp["result"]["tools"]}
    assert {"hypercharge_query", "hypercharge_memory", "hypercharge_log", "hypercharge_blast_radius"} <= names


def test_tools_list_matches_definitions():
    """Test tools list matches definitions. (hypercharge-managed)"""
    req = {"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}}
    resp = handle_request(req, Path("/tmp"))
    assert resp["result"]["tools"] == TOOL_DEFINITIONS


# ---------------------------------------------------------------------------
# tools/call — hypercharge_query (mocked)
# ---------------------------------------------------------------------------


def test_tools_call_query_returns_content_structure():
    """Test tools call query returns content structure. (hypercharge-managed)"""
    with patch(
        "hypercharge.mcp_server._call_query",
        return_value="GROUNDED: hypercharge/context.py:203 run_grounded_query",
    ) as mock_q:
        req = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "hypercharge_query",
                "arguments": {"topic": "run_grounded_query", "budget": 800},
            },
        }
        resp = handle_request(req, Path("/tmp"))

    assert resp["id"] == 4
    result = resp["result"]
    assert "content" in result
    assert isinstance(result["content"], list)
    assert len(result["content"]) == 1
    item = result["content"][0]
    assert item["type"] == "text"
    assert "GROUNDED" in item["text"]
    mock_q.assert_called_once()


def test_tools_call_query_default_budget():
    """_call_query is called with args dict containing no explicit budget."""
    captured: list[dict] = []

    def fake_call_query(root, args):
        """Fake call query. Args: root, args. Returns: 'ok'. (hypercharge-managed)"""
        captured.append(args)
        return "ok"

    with patch("hypercharge.mcp_server._call_query", side_effect=fake_call_query):
        req = {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "hypercharge_query",
                "arguments": {"topic": "cli structure"},
            },
        }
        resp = handle_request(req, Path("/tmp"))

    text = resp["result"]["content"][0]["text"]
    assert "ok" in text
    assert captured[0]["topic"] == "cli structure"


# ---------------------------------------------------------------------------
# tools/call — hypercharge_memory (mocked)
# ---------------------------------------------------------------------------


def test_tools_call_memory_returns_text():
    """Memory result gets ## Session Memory header prepended."""
    with patch("hypercharge.mcp_server._call_memory", return_value="session hit: deploy"):
        req = {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "hypercharge_memory",
                "arguments": {"query": "deploy"},
            },
        }
        resp = handle_request(req, Path("/tmp"))

    text = resp["result"]["content"][0]["text"]
    assert "session hit: deploy" in text
    assert text.startswith("## Session Memory")


# ---------------------------------------------------------------------------
# tools/call — hypercharge_log (mocked)
# ---------------------------------------------------------------------------


def test_tools_call_log_returns_confirmation():
    """Log tool returns the confirmation sentinel from _call_log."""
    with patch("hypercharge.mcp_server._call_log", return_value="\u2713 Logged to session."):
        req = {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {
                "name": "hypercharge_log",
                "arguments": {"file": "hypercharge/cli.py", "note": "added mcp-server"},
            },
        }
        resp = handle_request(req, Path("/tmp"))

    assert resp["result"]["content"][0]["text"] == "\u2713 Logged to session."


# ---------------------------------------------------------------------------
# _format_query_text / _format_memory_text unit tests
# ---------------------------------------------------------------------------


def test_format_query_text_adds_header():
    """Test format query text adds header. (hypercharge-managed)"""
    out = _format_query_text("some text without header")
    assert out.startswith("## Graph Context\n")


def test_format_query_text_wraps_path_line_citations():
    """Test format query text wraps path line citations. (hypercharge-managed)"""
    out = _format_query_text("see hypercharge/context.py:42 for details")
    assert "`hypercharge/context.py:42`" in out


def test_format_query_text_no_duplicate_header():
    """Test format query text no duplicate header. (hypercharge-managed)"""
    text = "## Graph Context\nalready formatted"
    out = _format_query_text(text)
    assert out.count("## Graph Context") == 1


def test_format_memory_text_adds_header():
    """Test format memory text adds header. (hypercharge-managed)"""
    out = _format_memory_text("past decision: use sqlite")
    assert out.startswith("## Session Memory\n")


def test_format_memory_text_preserves_existing_sections():
    """Test format memory text preserves existing sections. (hypercharge-managed)"""
    text = "## Decisions\nuse sqlite"
    out = _format_memory_text(text)
    assert out == text  # already has ## header — unchanged


def test_format_query_empty_passthrough():
    """Test format query empty passthrough. (hypercharge-managed)"""
    assert _format_query_text("") == ""


def test_format_memory_empty_passthrough():
    """Test format memory empty passthrough. (hypercharge-managed)"""
    assert _format_memory_text("") == ""


# ---------------------------------------------------------------------------
# Unknown method / tool
# ---------------------------------------------------------------------------


def test_unknown_method_returns_error():
    """Test unknown method returns error. (hypercharge-managed)"""
    req = {"jsonrpc": "2.0", "id": 8, "method": "ping", "params": {}}
    resp = handle_request(req, Path("/tmp"))
    assert "error" in resp
    assert resp["error"]["code"] == -32601


def test_unknown_tool_name_returns_error():
    """Test unknown tool name returns error. (hypercharge-managed)"""
    req = {
        "jsonrpc": "2.0",
        "id": 9,
        "method": "tools/call",
        "params": {"name": "does_not_exist", "arguments": {}},
    }
    resp = handle_request(req, Path("/tmp"))
    assert "error" in resp
    assert resp["error"]["code"] == -32601


# ---------------------------------------------------------------------------
# register_mcp_server
# ---------------------------------------------------------------------------


def test_register_mcp_server_creates_entry():
    """Test register mcp server creates entry. (hypercharge-managed)"""
    from hypercharge.claude_deploy import register_mcp_server

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        changed = register_mcp_server(root)
        assert changed is True
        config = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))
        entry = config["mcpServers"]["hypercharge"]
        assert entry["command"] == "hypercharge"
        assert "mcp-server" in entry["args"]
        # resolve() handles /var → /private/var symlink on macOS
        assert str(root.resolve()) in entry["args"]


def test_register_mcp_server_idempotent():
    """Test register mcp server idempotent. (hypercharge-managed)"""
    from hypercharge.claude_deploy import register_mcp_server

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        first = register_mcp_server(root)
        second = register_mcp_server(root)
        assert first is True
        assert second is False


def test_register_mcp_server_preserves_existing_keys():
    """Test register mcp server preserves existing keys. (hypercharge-managed)"""
    from hypercharge.claude_deploy import register_mcp_server

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mcp_path = root / ".mcp.json"
        mcp_path.write_text(
            json.dumps({"mcpServers": {"other-tool": {"command": "x"}}}),
            encoding="utf-8",
        )
        register_mcp_server(root)
        config = json.loads(mcp_path.read_text(encoding="utf-8"))
        assert "other-tool" in config["mcpServers"]
        assert "hypercharge" in config["mcpServers"]
        # register_mcp_server must NOT create or write mcpServers into .claude/settings.json
        assert not (root / ".claude/settings.json").exists()


def test_register_mcp_server_entry_is_stdio():
    """The Claude .mcp.json entry declares type stdio (parity with the Cursor entry)."""
    from hypercharge.claude_deploy import register_mcp_server

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        register_mcp_server(root)
        entry = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["hypercharge"]
        assert entry["type"] == "stdio"


def test_register_mcp_server_backs_up_malformed_file():
    """A malformed .mcp.json is backed up, not silently discarded."""
    from hypercharge.claude_deploy import register_mcp_server

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".mcp.json").write_text("{ this is not json", encoding="utf-8")
        register_mcp_server(root)
        assert (root / ".mcp.json.bak").is_file()
        assert "hypercharge" in json.loads((root / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]


def test_teardown_strips_mcp_entry_preserving_others():
    """Teardown removes the hypercharge entry from .mcp.json and keeps co-resident servers."""
    from hypercharge.claude_deploy import register_mcp_server
    from hypercharge.teardown_cmd import _strip_claude_mcp

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".mcp.json").write_text(
            json.dumps({"mcpServers": {"other": {"command": "x"}}}), encoding="utf-8"
        )
        register_mcp_server(root)
        assert "hypercharge" in json.loads((root / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]

        assert _strip_claude_mcp(root / ".mcp.json", dry_run=False) is True
        servers = json.loads((root / ".mcp.json").read_text(encoding="utf-8")).get("mcpServers", {})
        assert "hypercharge" not in servers
        assert "other" in servers
