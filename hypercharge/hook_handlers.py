"""Cursor hook handlers — testable Python (stdin JSON → stdout JSON)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hypercharge.answer_gate import assess_answer_text, format_answer_gate_message
from hypercharge.context_packet_cmd import build_context_packet
from hypercharge.turn_delta import build_turn_delta
from hypercharge.grounding_session import (
    grounding_policy,
    is_path_grounded,
    load_grounding,
    normalize_repo_path,
    record_approved_path,
)
from hypercharge.runtime_paths import runtime_json_path
from hypercharge.graph_refresh import enqueue_graph_refresh
from hypercharge.graph_freshness import graph_stale_reason
from hypercharge.turn_tracker import (
    format_stop_reminder,
    is_git_commit_command,
    load_turn_state,
    record_turn_commit,
    record_turn_edit,
    reset_turn_state,
    save_turn_state,
)

_WRITE_TOOLS = frozenset(
    {"Write", "StrReplace", "EditNotebook", "write", "search_replace", "apply_patch", "ApplyPatch"}
)
_READ_TOOLS = frozenset(
    {"Read", "read", "Grep", "grep", "SemanticSearch", "Glob", "glob", "codebase_search"}
)
_SHELL_TOOLS = frozenset({"Shell", "shell", "run_terminal_cmd", "Bash", "bash"})
_DELETE_TOOLS = frozenset({"Delete", "delete"})
_MCP_TOOLS = frozenset({"CallMcpTool", "call_mcp_tool", "mcp_tool", "FetchMcpResource"})
_PATHLESS_READ_TOOLS = frozenset(
    {"Grep", "grep", "SemanticSearch", "Glob", "glob", "codebase_search"}
)
_TASK_TOOLS = frozenset({"Task", "task", "Agent", "agent"})
_NETWORK_TOOLS = frozenset({"WebFetch", "WebSearch"})
_PATH_KEYS = ("path", "file_path", "target_file", "filePath", "notebook_path")


def _lookup_file_context(root: Path, path: str, budget: int = 200) -> str:
    """Quick graph lookup for a specific file path. Returns empty string on failure."""
    try:
        from hypercharge.context import run_grounded_query

        # build=False: an advisory hook must never trigger a synchronous graph build.
        _code, text = run_grounded_query(
            root, f"what is {Path(path).name} {path}", budget=budget, build=False
        )
        if text.strip():
            return text.strip()
    except Exception:
        pass
    return ""


def _deny_pre_tool(root: Path, tool: str, msg: str, **extra: Any) -> dict[str, Any]:
    """Internal _deny_pre_tool. Args: root, tool, msg. Returns: out. (hypercharge-managed)"""
    from hypercharge.audit_log import append_audit

    append_audit(root, hook="pre-tool", tool=tool, decision="deny", detail=msg)
    out: dict[str, Any] = {"permission": "deny", "agent_message": msg}
    out.update(extra)
    return out

def _advisory_or_deny(
    root: Path, tool: str, policy: str, msg: str, **extra: Any
) -> dict[str, Any]:
    """Deny when policy is block; otherwise allow with advisory agent_message."""
    if policy == "block":
        return _deny_pre_tool(root, tool, msg, **extra)
    out: dict[str, Any] = {"permission": "allow", "agent_message": msg}
    out.update(extra)
    return out


def _extract_shell_command(payload: dict[str, Any]) -> str:
    """Internal _extract_shell_command. Args: payload. Returns: ''. (hypercharge-managed)"""
    tool_input = payload.get("tool_input") or payload.get("input") or payload.get("arguments") or {}
    if isinstance(tool_input, str):
        return tool_input.strip()
    if isinstance(tool_input, dict):
        return str(
            tool_input.get("command")
            or tool_input.get("cmd")
            or tool_input.get("script")
            or ""
        ).strip()
    return ""


def _extract_tool_path(payload: dict[str, Any]) -> str | None:
    """Internal _extract_tool_path. Args: payload. Returns: None. (hypercharge-managed)"""
    tool_input = payload.get("tool_input") or payload.get("input") or payload.get("arguments") or {}
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except json.JSONDecodeError:
            return None
    if not isinstance(tool_input, dict):
        return None
    for key in _PATH_KEYS:
        val = tool_input.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    for key, val in tool_input.items():
        if key.endswith("path") and isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _is_semantic_log_command(cmd: str) -> bool:
    """True when a shell command is an agent `hypercharge log` semantic note/decision."""
    import re

    if not re.search(r"\bhypercharge\b[^\n]*\blog\b", cmd or ""):
        return False
    return "--note" in cmd or "--decision" in cmd


def handle_session_start(root: Path, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Inject bounded context packet at session start."""
    _ = payload
    if not runtime_json_path(root).is_file():
        return {}
    # Nothing synchronous on the session-open critical path — no graph build and no
    # memory-index rebuild. The index is kept fresh incrementally by the after-edit
    # hook and fully rebuilt at wrapup; a slightly stale recall here is acceptable.
    grounding = load_grounding(root)
    queried = grounding.get("queried_paths") or []
    lean = graph_stale_reason(root) is None
    if len(queried) >= 3:
        budget = 350
    elif lean:
        budget = 500
    else:
        budget = 800
    packet = build_context_packet(root, budget=budget, lean=lean)
    if not packet.strip():
        return {}
    return {
        "additional_context": (
            "<!-- hypercharge-managed: context-packet -->\n" + packet
        ),
    }


def build_prompt_grounding_digest(root: Path, prompt: str, *, budget: int = 350) -> str:
    """Lightweight session + graph digest for a user prompt (hook-safe budget)."""
    from hypercharge.knowledge_cmd import _session_knowledge
    from hypercharge.context import run_grounded_query

    prompt = (prompt or "").strip()
    if len(prompt) < 12:
        return ""
    parts: list[str] = ["## Prompt grounding"]
    session_text = _session_knowledge(root, prompt)
    if session_text.strip():
        parts.append(session_text.strip())
    # build=False: prompt grounding runs on every turn — it must not build the graph.
    code, graph_text = run_grounded_query(root, prompt, budget=budget, build=False)
    if graph_text.strip():
        parts.append("## Graph")
        parts.append(graph_text.strip())
    if code == 0:
        from hypercharge.grounding_gate import extract_citations
        from hypercharge.grounding_session import record_query_success

        cites = extract_citations(graph_text)
        record_query_success(root, [p for p, _ in cites])
    body = "\n".join(parts).strip()
    max_chars = max(200, budget * 4)
    if len(body) > max_chars:
        return body[: max_chars - 20] + "\n… [grounding clipped]"
    return body


def handle_before_submit_prompt(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Per-turn delta + prompt-scoped knowledge digest."""
    if not runtime_json_path(root).is_file():
        return {}
    reset_turn_state(root)
    delta = build_turn_delta(root, budget=400)
    prompt = str(
        payload.get("prompt")
        or payload.get("text")
        or payload.get("message")
        or payload.get("user_message")
        or ""
    )
    prompt_stripped = prompt.strip()
    if not prompt_stripped or len(prompt_stripped) < 20:
        grounding = ""
    elif len(prompt_stripped) > 200:
        grounding = build_prompt_grounding_digest(root, prompt, budget=600)
    else:
        grounding = build_prompt_grounding_digest(root, prompt, budget=350)
    chunks = []
    if delta.strip():
        chunks.append("<!-- hypercharge-managed: turn-delta -->\n" + delta)
    if grounding.strip():
        chunks.append("<!-- hypercharge-managed: prompt-grounding -->\n" + grounding)
    if not chunks:
        return {}
    return {"additional_context": "\n\n".join(chunks)}


def handle_pre_tool_use(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Pre-tool policy — block or advise based on grounding_gate."""
    tool = str(payload.get("tool_name") or payload.get("name") or "")
    target = _extract_tool_path(payload)
    policy = grounding_policy(root)

    if tool in _NETWORK_TOOLS:
        return {"permission": "allow"}

    if tool in _SHELL_TOOLS:
        from hypercharge.shell_gate import assess_shell_command

        cmd = _extract_shell_command(payload)
        assessment = assess_shell_command(cmd)
        if assessment.safe:
            return {"permission": "allow"}
        if not assessment.needs_grounding:
            if "network binary" in assessment.reason:
                return {
                    "permission": "allow",
                    "agent_message": (
                        "HEADS UP: network command detected — ensure this is intentional "
                        "and no secrets are exposed."
                    ),
                }
            if "subshell" in assessment.reason:
                return {
                    "permission": "allow",
                    "agent_message": "HEADS UP: subshell substitution detected — verify this is safe.",
                }
            return {"permission": "allow"}
        ungrounded = [p for p in assessment.paths if not is_path_grounded(root, p)]
        if ungrounded:
            sample = ", ".join(ungrounded[:3])
            file_ctx = _lookup_file_context(root, ungrounded[0])
            msg = f"Shell access to ungrounded paths ({sample})."
            if file_ctx:
                msg += f"\n\nGraph context:\n{file_ctx}"
            else:
                msg += " Run `hypercharge knowledge` first."
            return _advisory_or_deny(root, tool, policy, msg)
        for p in assessment.paths:
            record_approved_path(root, p)
        return {"permission": "allow"}

    if tool in _TASK_TOOLS:
        return {"permission": "allow"}

    if tool in _READ_TOOLS and not target:
        return {"permission": "allow"}

    if tool in _READ_TOOLS and target:
        target = normalize_repo_path(root, target)
        if target:
            record_approved_path(root, target)
            from hypercharge.read_tracker import record_read_snapshot

            record_read_snapshot(root, target)
        return {"permission": "allow"}

    if tool in _DELETE_TOOLS or tool in _WRITE_TOOLS:
        if not target:
            return {"permission": "allow"}

        target = normalize_repo_path(root, target)
        if not is_path_grounded(root, target):
            file_ctx = _lookup_file_context(root, target)
            msg = f"`{target}` hasn't been queried this session."
            if file_ctx:
                msg += f"\n\nGraph context:\n{file_ctx}"
            else:
                msg += " Run `hypercharge knowledge` or Read the file first."
            return _advisory_or_deny(root, tool, policy, msg)

        from hypercharge.read_tracker import read_before_write_ok

        ok, reason = read_before_write_ok(root, target)
        if not ok:
            return _advisory_or_deny(root, tool, policy, reason)

        # Blast radius injection for write/delete on grounded files
        try:
            from hypercharge.blast_radius import analyse, format_for_injection

            br = analyse(root, target)
            if br.risk_level in ("medium", "high") or (
                br.risk_level == "low" and br.callsite_count > 0
            ) or br.risk_level == "unknown":
                br_text = format_for_injection(br)
                return {"permission": "allow", "agent_message": br_text}
        except Exception:
            pass

        return {"permission": "allow"}

    return {"permission": "allow"}


def _repo_relative(root: Path, raw: str) -> str | None:
    """Repo-relative POSIX path when ``raw`` resolves inside ``root``, else None.

    Stricter than ``normalize_repo_path`` (which is lenient for grounding-citation
    matching and will happily coin a repo-relative-looking tail from a foreign path).
    An edit outside the repo — e.g. an in-session workflow script under ``~/.claude/`` —
    must return None so it is never counted as a repo edit, queued for the graph, or
    written to the session log. That false counting is what drove the Stop-hook loop.
    """
    raw = (raw or "").strip().strip("'\"")
    if not raw:
        return None
    root = root.resolve()
    try:
        candidate = Path(raw) if raw.startswith("/") else root / raw
        rel = candidate.resolve().relative_to(root)
    except (ValueError, OSError):
        return None
    return str(rel).replace("\\", "/")


def handle_after_file_edit(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Queue graph refresh, auto-drain, auto-log file touch."""
    path = _extract_tool_path(payload)
    if not path:
        for key in _PATH_KEYS:
            val = payload.get(key)
            if isinstance(val, str) and val.strip():
                path = val.strip()
                break
    if path:
        rel = _repo_relative(root, path)
        if rel is None:
            # Edit landed outside the repo (e.g. an in-session workflow script) — do not
            # count it as a repo edit, feed it to the graph, or log it to the session.
            return {}
        record_turn_edit(root, rel)
        record_approved_path(root, path)
        # Queue a graph refresh but never build synchronously inside a hook —
        # the queue is drained at wrapup / start-day, off the agent's critical path.
        enqueue_graph_refresh(root, path)
        try:
            from hypercharge.log_cmd import run_log
            from hypercharge.ui.console import HyperConsole

            run_log(root, HyperConsole(plain=True), files=[path], note="auto: file edited (hook)")
        except (OSError, ValueError, TypeError):
            pass
        try:
            from hypercharge.memory_index import append_memory_entry

            append_memory_entry(root, path=rel, note="file edited")
        except (ImportError, Exception):
            pass
    return {}


def handle_after_shell(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Record pytest/test command results for test oracle."""
    from hypercharge.test_oracle import is_test_command, record_test_result

    cmd = _extract_shell_command(payload)
    if is_git_commit_command(cmd):
        record_turn_commit(root)
    if _is_semantic_log_command(cmd):
        from hypercharge.turn_tracker import record_turn_semantic_log

        record_turn_semantic_log(root, note="session log via shell")
    if not is_test_command(cmd):
        return {}
    tool_output = payload.get("tool_output") or payload.get("output") or {}
    exit_code = 0
    if isinstance(tool_output, dict):
        exit_code = int(tool_output.get("exit_code") or tool_output.get("exitCode") or 0)
    elif payload.get("exit_code") is not None:
        exit_code = int(payload.get("exit_code"))
    record_test_result(root, cmd=cmd, exit_code=exit_code)
    if exit_code != 0:
        return {
            "additional_context": (
                "<!-- hypercharge-managed: test-oracle -->\n"
                f"Last test run failed (exit {exit_code}). Do not claim fixed."
            ),
        }
    return {}


def handle_after_agent_response(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Answer-time enrichment — Stop advisories (session log, commit, grounding)."""
    text = str(
        payload.get("text")
        or payload.get("response")
        or payload.get("content")
        or payload.get("message")
        or ""
    )
    from hypercharge.test_oracle import claims_fixed_while_tests_red

    chunks: list[str] = []
    policy = grounding_policy(root)

    if claims_fixed_while_tests_red(text, root):
        if policy != "off":
            chunks.append(
                "Tests failed on last run — do not claim fixed until pytest passes."
            )

    stop_reminder = format_stop_reminder(root)
    if stop_reminder:
        # Emit the session-log / commit advisory at most once per turn. The Stop hook
        # can re-fire many times within a single turn (e.g. while the agent idles waiting
        # on a background job); without this cap the same reminder loops every cycle and
        # can never be satisfied. reset_turn_state (each new prompt) clears the flag.
        state = load_turn_state(root)
        if not state.get("stop_reminded"):
            chunks.append(stop_reminder)
            state["stop_reminded"] = True
            save_turn_state(root, state)

    if policy != "off":
        # Don't nag an answer that already carries a grounded path:line citation —
        # the advisory is for genuinely ungrounded claims, not cited ones. A single
        # on-disk-valid citation is enough to suppress it.
        from hypercharge.grounding_gate import extract_citations, validate_citations_exist

        cited = validate_citations_exist(root, extract_citations(text, require_line=True))
        if not cited:
            assessment = assess_answer_text(text, root)
            if not assessment.ok:
                chunks.append(
                    "<!-- hypercharge-managed: grounding-advisory -->\n"
                    f"**Grounding note** ({assessment.claim_count} repo claim(s) detected): "
                    "Some claims in this response may lack source citations. "
                    "For your next message, consider verifying with `hypercharge query` "
                    "if these points are important to the user."
                )

    out: dict[str, Any] = {}
    if chunks:
        out["additional_context"] = "\n\n".join(chunks)

    # No separate followup_message for the missing session log: format_stop_reminder
    # above already carries that reminder (for every policy), and emitting both sent
    # the agent the same 'run hypercharge log' note twice under block policy.
    return out


def dispatch_hook(event: str, root: Path, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Dispatch a hook event to its handler; session-scope state when a session id is present."""
    payload = payload or {}
    sid = payload.get("session_id")
    if sid:
        from hypercharge.session_scope import set_session_id

        set_session_id(sid)
    if event in ("session-start", "sessionStart"):
        return handle_session_start(root, payload)
    if event in ("before-prompt", "beforeSubmitPrompt"):
        return handle_before_submit_prompt(root, payload)
    if event in ("pre-tool", "preToolUse"):
        return handle_pre_tool_use(root, payload)
    if event in ("after-edit", "afterFileEdit"):
        return handle_after_file_edit(root, payload)
    if event in ("after-shell",):
        return handle_after_shell(root, payload)
    if event in ("after-response", "afterAgentResponse"):
        return handle_after_agent_response(root, payload)
    return {}
