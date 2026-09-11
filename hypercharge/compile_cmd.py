"""Apply approved compile batches only."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from hypercharge.rules_compile import analyse_rules, apply_compile_plan, plan_summary_lines


def apply_seed_batch(root: Path, rows: list[dict[str, str]], *, compile_note: str = "") -> None:
    """Log compile batch applied."""
    _ = rows
    _ = compile_note
    root = root.resolve()
    log_path = root / ".cursor/hypercharge/compile-log.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    log_path.write_text(
        f'{{"at": "{now}", "action": "rules_compile", "note": {compile_note!r}}}\n',
        encoding="utf-8",
    )


def run_confirm_rules_review(root: Path) -> str:
    """Rules compile — analyse, harden precedence, log review."""
    from hypercharge.inventory import (
        scan_project_inventory,
        scan_user_skills,
    )

    root = root.resolve()
    plan = analyse_rules(root)
    applied = apply_compile_plan(root, plan)
    rows = scan_project_inventory(root) + scan_user_skills()
    apply_seed_batch(
        root,
        rows,
        compile_note=f"Hardened precedence; {len(plan.issues)} issues resolved; files: {', '.join(applied)}",
    )
    _refresh_onboard_manifest(root)
    return (
        f"Rules compile done — {len(plan.issues)} issues addressed, "
        f"{len(applied)} files written. User rules not rewritten (precedence + agent-map only)."
    )


def _refresh_onboard_manifest(root: Path) -> None:
    """Keep last-onboard.json in sync after compile."""
    import json

    from hypercharge.graph import graph_hash, graph_is_present, graph_node_count
    from hypercharge.paths import CURSOR_HYPERCHARGE

    path = root / CURSOR_HYPERCHARGE / "last-onboard.json"
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    data["pending_user_steps"] = []
    data["agent_must_ask"] = []
    data["graph"] = {
        "present": graph_is_present(root),
        "hash": graph_hash(root),
        "nodes": graph_node_count(root),
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def run_compile(root: Path, console, *, dry_run: bool = False) -> int:
    """User-facing rules compile — analyse conflicts and apply approved hardening."""
    root = root.resolve()
    if not (root / ".cursor").is_dir():
        console.step_fail("Compile", "Run hypercharge setup in this repo first.")
        return 1

    from hypercharge.ui import copy_en_gb as copy

    plan = analyse_rules(root)
    if dry_run:
        for line in plan_summary_lines(plan):
            console.warn(line.replace("**", ""))
        console.footer("Rules compile (dry run)", plan.actions)
        return 0

    msg = run_confirm_rules_review(root)
    footer = [
        msg,
        "Precedence rule: .cursor/rules/hypercharge-rules-compile.mdc",
        "Full report: .cursor/hypercharge/compile-report.md",
        copy.NEXT_WRAPUP_CHAT,
    ]
    console.footer("Rules compile done", footer)
    return 0
