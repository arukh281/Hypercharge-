"""Claude Code hook adapter — stdin/out JSON ↔ hypercharge hook_handlers."""

from __future__ import annotations

import json
from typing import Any

from hypercharge.hook_handlers import dispatch_hook

_CLAUDE_HOOK_EVENT: dict[str, str] = {
    "session-start": "SessionStart",
    "before-prompt": "UserPromptSubmit",
    "pre-tool": "PreToolUse",
    "after-edit": "PostToolUse",
    "after-shell": "PostToolUse",
    "after-response": "Stop",
}

_CLAUDE_TO_HC_TOOL: dict[str, str] = {
    "Bash": "Shell",
    "Write": "Write",
    "Edit": "StrReplace",
    "Read": "Read",
    "Grep": "Grep",
    "Glob": "Glob",
    "Delete": "Delete",
    "Task": "Task",
    "Agent": "Task",
    "WebFetch": "WebFetch",    # pass through unchanged
    "WebSearch": "WebSearch",  # pass through unchanged
}


def _hc_tool_name(claude_tool: str) -> str:
    """Internal _hc_tool_name. Args: claude_tool. Returns: _CLAUDE_TO_HC_TOOL.get(claude_tool, claude_tool). (hypercharge-managed)"""
    if claude_tool.startswith("mcp__"):
        return "CallMcpTool"
    return _CLAUDE_TO_HC_TOOL.get(claude_tool, claude_tool)


def claude_payload_to_handler(event: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Map Claude Code hook stdin JSON to hook_handlers payload."""
    if event == "session-start":
        return {}
    if event == "before-prompt":
        return {
            "prompt": payload.get("prompt")
            or payload.get("text")
            or payload.get("message")
            or "",
        }
    if event == "pre-tool":
        tool_input = payload.get("tool_input") or {}
        return {
            "tool_name": _hc_tool_name(str(payload.get("tool_name") or "")),
            "tool_input": tool_input,
            "arguments": tool_input,
        }
    if event == "after-edit":
        tool = str(payload.get("tool_name") or "")
        if tool not in ("Write", "Edit"):
            return {}
        tool_input = payload.get("tool_input") or {}
        path = str(tool_input.get("file_path") or tool_input.get("path") or "").strip()
        hc_tool = "StrReplace" if tool == "Edit" else "Write"
        return {
            "tool_name": hc_tool,
            "tool_input": {"path": path},
            "file_path": path,
        }
    if event == "after-shell":
        tool = str(payload.get("tool_name") or "")
        if tool != "Bash":
            return {}
        tool_input = payload.get("tool_input") or {}
        return {
            "tool_name": "Shell",
            "tool_input": tool_input,
            "tool_output": payload.get("tool_response") or payload.get("tool_output") or {},
        }
    if event == "after-response":
        return {
            "text": payload.get("last_assistant_message")
            or payload.get("text")
            or payload.get("response")
            or payload.get("content")
            or "",
        }
    return payload


def handler_result_to_claude(event: str, result: dict[str, Any]) -> dict[str, Any]:
    """Map hook_handlers output to Claude Code hook stdout JSON."""
    hook_event = _CLAUDE_HOOK_EVENT.get(event, event)
    if not result:
        return {}

    if event == "pre-tool":
        # Advisory only: inject context, never a permission decision. Returning a
        # permissionDecision here would bypass Claude Code's own permission prompt.
        if result.get("agent_message"):
            return {
                "hookSpecificOutput": {
                    "hookEventName": hook_event,
                    "additionalContext": str(result["agent_message"]),
                }
            }
        return {}

    if event == "after-response":
        ctx = str(result.get("additional_context") or "").strip()
        followup = str(result.get("followup_message") or "").strip()
        combined = "\n\n".join(x for x in [ctx, followup] if x)
        if combined:
            return {
                "hookSpecificOutput": {
                    "hookEventName": hook_event,
                    "additionalContext": combined,
                }
            }
        return {}

    ctx = str(result.get("additional_context") or "").strip()
    if not ctx:
        return {}
    return {
        "hookSpecificOutput": {
            "hookEventName": hook_event,
            "additionalContext": ctx,
        }
    }


def claude_pre_tool_warn(message: str) -> dict[str, Any]:
    """Surface a message as pre-tool context — never a permission decision."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": message,
        }
    }


def run_claude_hook(event: str, root, payload: dict[str, Any]) -> dict[str, Any]:
    """Dispatch one Claude hook event; return Claude-shaped stdout JSON."""
    from pathlib import Path

    from hypercharge.session_scope import set_session_id

    root = Path(root).resolve()
    set_session_id(payload.get("session_id"))
    handler_payload = claude_payload_to_handler(event, payload)
    if event == "after-edit" and not handler_payload:
        return {}
    result = dispatch_hook(event, root, handler_payload)
    return handler_result_to_claude(event, result)


def run_claude_hook_stdio(event: str, root, raw_stdin: str) -> str:
    """Parse stdin, run hook, return JSON string for stdout."""
    payload: dict[str, Any] = {}
    if raw_stdin.strip():
        try:
            payload = json.loads(raw_stdin)
        except json.JSONDecodeError:
            if event == "pre-tool":
                return json.dumps(
                    claude_pre_tool_warn("Hook stdin was not valid JSON — cannot parse tool input.")
                )
            return "{}"
    return json.dumps(run_claude_hook(event, root, payload))
