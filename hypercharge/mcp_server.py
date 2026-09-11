"""Hypercharge MCP server — stdio JSON-RPC transport for native Claude tool calls."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

TOOL_DEFINITIONS = [
    {
        "name": "hypercharge_query",
        "description": "Query the Hypercharge code graph for grounded repo context.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Question or topic to query"},
                "budget": {
                    "type": "number",
                    "description": "Token budget (default 800)",
                },
            },
            "required": ["topic"],
        },
    },
    {
        "name": "hypercharge_memory",
        "description": "Search Hypercharge session memory for past decisions and notes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "hypercharge_log",
        "description": "Log a note about a file to the current Hypercharge session.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Repo-relative file path"},
                "note": {"type": "string", "description": "Note to record"},
            },
            "required": ["file", "note"],
        },
    },
    {
        "name": "hypercharge_blast_radius",
        "description": (
            "Analyse the blast radius of a file — how many other files/tests depend on it. "
            "Call this before editing a file to understand potential impact."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": {
                    "type": "string",
                    "description": "Repo-relative file path to analyse",
                },
            },
            "required": ["file"],
        },
    },
    {
        "name": "hypercharge_session_note",
        "description": (
            "Append a note to the repo session store (.cursor/session/). "
            "Use for session events and quick captures during agent work."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["note", "decision"],
                    "description": (
                        "'note' appends to .cursor/session/SESSION_NOTES.md; "
                        "'decision' records via hypercharge log --decision"
                    ),
                },
                "content": {
                    "type": "string",
                    "description": "Text to append (will be written verbatim with a trailing newline)",
                },
            },
            "required": ["type", "content"],
        },
    },
]


def _call_query(root: Path, args: dict) -> str:
    """Internal _call_query. Args: root, args. Returns: text. (hypercharge-managed)"""
    from hypercharge.context import run_grounded_query

    topic: str = args["topic"]
    budget: int = int(args.get("budget") or 800)
    _code, text = run_grounded_query(root, topic, budget=budget)
    return text


def _call_memory(root: Path, args: dict) -> str:
    """Internal _call_memory. Args: root, args. Returns: _session_knowledge(root, args['query']). (hypercharge-managed)"""
    from hypercharge.knowledge_cmd import _session_knowledge

    return _session_knowledge(root, args["query"])


def _call_blast_radius(root: Path, args: dict) -> str:
    """Internal _call_blast_radius. Args: root, args. Returns: formatted blast radius string. (hypercharge-managed)"""
    from hypercharge.blast_radius import analyse, format_for_injection

    file_path: str = args["file"]
    br = analyse(root, file_path)
    return format_for_injection(br)


def _call_session_note(root: Path, args: dict) -> str:
    """Append a note to .cursor/session/ (single session store)."""
    from datetime import datetime, timezone

    note_type: str = args["type"]
    content: str = args["content"]

    if note_type == "decision":
        from hypercharge.log_cmd import run_log
        from hypercharge.ui.console import HyperConsole

        run_log(root, HyperConsole(plain=True), decision=content.strip())
        return "\u2713 Recorded decision in session memory"

    if note_type != "note":
        raise ValueError(f"Unknown note type {note_type!r}; expected 'note' or 'decision'")

    dest = root / ".cursor/session/SESSION_NOTES.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    block = f"\n### [{stamp}]\n{content.rstrip()}\n"
    with dest.open("a", encoding="utf-8") as fh:
        fh.write(block if block.endswith("\n") else block + "\n")
    return f"\u2713 Appended to {dest.relative_to(root)}"


def _call_log(root: Path, args: dict) -> str:
    """Internal _call_log. Args: root, args. Returns: confirmation string. (hypercharge-managed)"""
    from hypercharge.log_cmd import run_log
    from hypercharge.ui.console import HyperConsole

    console = HyperConsole(plain=True)
    run_log(root, console, files=[args["file"]], note=args["note"])
    return "\u2713 Logged to session."


def _format_query_text(text: str) -> str:
    """Wrap path:line citations in backticks and add ## Graph Context header."""
    if not text.strip():
        return text
    text = re.sub(r"(?<![`\w])([\w./\-]+\.py:\d+)", r"`\1`", text)
    if not text.lstrip().startswith("## Graph Context"):
        text = "## Graph Context\n" + text
    return text


def _format_memory_text(text: str) -> str:
    """Preserve ## sections and add ## Session Memory header if absent."""
    if not text.strip():
        return text
    if not text.lstrip().startswith("##"):
        text = "## Session Memory\n" + text
    return text


def _tool_result(text: str) -> dict:
    """Internal _tool_result. Args: text. Returns: {'content': [{'type': 'text', 'text': text}]}. (hypercharge-managed)"""
    return {"content": [{"type": "text", "text": text}]}


def _error_result(message: str) -> dict:
    """Internal _error_result. Args: message. Returns: {'content': [{'type': 'text', 'text': f'error: {me. (hypercharge-managed)"""
    return {"content": [{"type": "text", "text": f"error: {message}"}], "isError": True}


def handle_request(req: dict, root: Path) -> dict:
    """Dispatch one JSON-RPC request; always return a dict."""
    req_id = req.get("id")
    method = req.get("method", "")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "hypercharge", "version": "1.0"},
            },
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOL_DEFINITIONS},
        }

    if method == "tools/call":
        params = req.get("params") or {}
        tool_name: str = params.get("name", "")
        tool_args: dict = params.get("arguments") or {}

        try:
            if tool_name == "hypercharge_query":
                text = _format_query_text(_call_query(root, tool_args))
            elif tool_name == "hypercharge_memory":
                text = _format_memory_text(_call_memory(root, tool_args))
            elif tool_name == "hypercharge_log":
                text = _call_log(root, tool_args)
            elif tool_name == "hypercharge_blast_radius":
                text = _call_blast_radius(root, tool_args)
            elif tool_name == "hypercharge_session_note":
                text = _call_session_note(root, tool_args)
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
                }
        except Exception as exc:  # noqa: BLE001
            return {"jsonrpc": "2.0", "id": req_id, "result": _error_result(str(exc))}

        return {"jsonrpc": "2.0", "id": req_id, "result": _tool_result(text)}

    # Notifications (no id) — silently ignore
    if req_id is None:
        return {}

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": "Method not found"},
    }


def main() -> None:
    """Run the MCP server, reading JSON-RPC messages from stdin line by line."""
    root = Path(os.environ.get("HYPERCHARGE_REPO_ROOT", os.getcwd())).resolve()

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = handle_request(req, root)
        except json.JSONDecodeError as exc:
            resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {exc}"},
            }
        except Exception as exc:  # noqa: BLE001
            resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": str(exc)},
            }

        # Notifications produce an empty dict — don't write anything
        if resp:
            print(json.dumps(resp), flush=True)
