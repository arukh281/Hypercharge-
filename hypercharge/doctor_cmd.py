"""Repo health check — rules, graph, session, loose ends."""

from __future__ import annotations

import json
from pathlib import Path

from hypercharge import __version__
from hypercharge.escalation import escalation_enabled, load_escalation_policy
from hypercharge.agent_target import deploys_claude, deploys_cursor, load_agent_target
from hypercharge.claude_deploy import claude_contract_health
from hypercharge.graph import graph_hash, graph_is_present
from hypercharge.hooks_deploy import hooks_health
from hypercharge.loose_ends import collect_loose_ends
from hypercharge.session import active_open_chats, load_lock, peek_current_chat_id
from hypercharge.templates_deploy import MANAGED_RULES
from hypercharge.ui.console import HyperConsole


def _suggested_fixes(root: Path, report: dict, ends: list) -> list[str]:
    """Internal _suggested_fixes. Args: root, report, ends. Returns: fixes. (hypercharge-managed)"""
    fixes: list[str] = []
    if not report["setup"]:
        fixes.append("hypercharge onboard --path <git_root>")
        return fixes
    if not report["managed_rules_ok"]:
        fixes.append("hypercharge setup --skip-dialogue --path <git_root>")
    if not report["graph_present"]:
        fixes.append("hypercharge wrapup --day --path <git_root>")
    for end in ends:
        if end.suggested and end.suggested not in fixes:
            fixes.append(end.suggested)
    if report["loose_ends"] > 0:
        fixes.append("hypercharge wrapup --start-day --path <git_root>")
    if report.get("hooks_issues"):
        fixes.append("hypercharge setup --skip-dialogue --path <git_root>")
    if not report.get("memory_index_present") and report.get("setup"):
        fixes.append("hypercharge memory-index --rebuild --path <git_root>")
    elif report.get("memory_index_stale"):
        fixes.append("hypercharge wrapup --path <git_root>  # rebuilds memory index")
    return fixes


def build_doctor_report(root: Path) -> dict:
    """Build doctor report. Args: root. Returns: report. (hypercharge-managed)"""
    root = root.resolve()
    target = load_agent_target(root)
    rules_dir = root / ".cursor/rules"
    managed_ok = all((rules_dir / name).is_file() for name in MANAGED_RULES)
    if not deploys_cursor(target):
        managed_ok = True
    claude_ok = not claude_contract_health(root) if deploys_claude(target) else True
    lock = load_lock(root)
    ends = collect_loose_ends(root)
    esc = load_escalation_policy(root)
    hook_issues = hooks_health(root) if (root / ".cursor").is_dir() else ["hooks_missing"]
    from hypercharge.memory_index import index_path

    memory_index_present = index_path(root).is_file() if (root / ".cursor").is_dir() else False
    from hypercharge.memory_index import memory_index_stale

    memory_stale = memory_index_stale(root) if memory_index_present else True

    report = {
        "hypercharge_version": __version__,
        "agent_target": target,
        "setup": (root / ".cursor").is_dir(),
        "managed_rules_ok": managed_ok,
        "claude_contract_ok": claude_ok,
        "managed_rules": list(MANAGED_RULES),
        "graph_present": graph_is_present(root),
        "graph_hash": graph_hash(root),
        "ready": managed_ok and graph_is_present(root),
        "current_chat": peek_current_chat_id(root),
        "active_threads": len(active_open_chats(root)),
        "loose_ends": len(ends),
        "loose_end_ids": [e.id for e in ends],
        "last_day_wrapup": lock.get("last_day_wrapup", "never"),
        "last_chat_wrapup": lock.get("last_chat_wrapup", "never"),
        "escalation_enabled": escalation_enabled(root),
        "escalation_mode": esc.get("mode", "ask"),
        "hooks_issues": hook_issues,
        "memory_index_present": memory_index_present,
        "memory_index_stale": memory_stale,
    }
    report["suggested_fixes"] = _suggested_fixes(root, report, ends)
    return report


def _doctor_exit_code(report: dict, *, tier: str = "ready") -> int:
    """tier=ready: setup + contract + hooks. tier=ideal: graph + no loose ends. tier=hooks/claude-hooks: managed hooks."""
    target = report.get("agent_target", "both")
    if not report["setup"]:
        return 1
    if deploys_cursor(target) and not report["managed_rules_ok"]:
        return 1
    if deploys_claude(target) and not report.get("claude_contract_ok", True):
        return 1
    if tier == "claude-hooks":
        claude_issues = [i for i in (report.get("hooks_issues") or []) if i.startswith("claude_")]
        return 0 if not claude_issues else 1
    if tier == "hooks":
        cursor_issues = [i for i in (report.get("hooks_issues") or []) if not i.startswith("claude_")]
        return 0 if not cursor_issues else 1
    if tier == "ready":
        if report.get("hooks_issues"):
            return 1
        if report.get("memory_index_present") and report.get("memory_index_stale"):
            return 1
        return 0
    if not report["graph_present"] or report["loose_ends"] > 0:
        return 1
    if report.get("memory_index_stale"):
        return 1
    return 0


def run_doctor(root: Path, console: HyperConsole, *, as_json: bool = False, tier: str = "ready") -> int:
    """Run doctor. Args: root, console. Returns: code. (hypercharge-managed)"""
    root = root.resolve()
    report = build_doctor_report(root)
    report["health_tier"] = tier
    report["ready"] = _doctor_exit_code(report, tier="ready") == 0
    report["ideal"] = _doctor_exit_code(report, tier="ideal") == 0
    code = _doctor_exit_code(report, tier=tier)

    if as_json:
        print(json.dumps(report, indent=2))
        return code

    if not report["setup"]:
        console.step_fail("Doctor", "Run hypercharge setup in this repo first.")
        return 1

    rows = [
        ("Agent target", "ok", report.get("agent_target", "both")),
        ("Managed rules", "ok" if report["managed_rules_ok"] else "warn", ", ".join(report["managed_rules"])),
        (
            "Claude contract",
            "ok" if report.get("claude_contract_ok", True) else "warn",
            "CLAUDE.md + project skill" if report.get("claude_contract_ok", True) else "run setup",
        ),
        ("Graph", "ok" if report["graph_present"] else "warn", str(report["graph_hash"] or "missing")),
        ("Ready", "ok" if report.get("ready") else "warn", "yes" if report.get("ready") else "check setup"),
        ("Current chat", "ok", report["current_chat"] or "none"),
        ("Active threads", "ok", str(report["active_threads"])),
        ("Loose ends", "ok" if report["loose_ends"] == 0 else "warn", str(report["loose_ends"])),
        ("Escalation", "ok" if report["escalation_enabled"] else "warn", report["escalation_mode"]),
        ("Last day wrapup", "ok", report["last_day_wrapup"]),
        (
            "Hooks",
            "ok" if not report.get("hooks_issues") else "warn",
            "ok" if not report.get("hooks_issues") else ", ".join(report["hooks_issues"][:3]),
        ),
        (
            "Memory index",
            "ok" if report.get("memory_index_present") and not report.get("memory_index_stale") else "warn",
            "stale" if report.get("memory_index_stale") else ("ok" if report.get("memory_index_present") else "missing"),
        ),
    ]
    console.health_table(rows)
    if report["loose_end_ids"]:
        console.warn("Loose ends: " + ", ".join(report["loose_end_ids"]) + " — run hypercharge wrapup --start-day")
    if report.get("suggested_fixes"):
        console.warn("Suggested fixes:")
        for fix in report["suggested_fixes"][:6]:
            console.warn(f"  → {fix}")
    return code
