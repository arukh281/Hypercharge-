"""Repo manager status — one-screen orientation."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from hypercharge.graph import graph_hash, graph_is_present
from hypercharge.loose_ends import collect_loose_ends
from hypercharge.paths import git_branch
from hypercharge.session import active_open_chats, peek_current_chat_id
from hypercharge.ui.console import HyperConsole


def _git_dirty(root: Path) -> list[str]:
    """Internal _git_dirty. Args: root. Returns: [ln[3:].strip() for ln in out.stdout.splitlines() . (hypercharge-managed)"""
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [ln[3:].strip() for ln in out.stdout.splitlines() if ln.strip()]


def build_status_report(root: Path) -> dict:
    """Build status report. Args: root. Returns: {'branch': git_branch(root), 'dirty_files': dirty[. (hypercharge-managed)"""
    root = root.resolve()
    ends = collect_loose_ends(root)
    dirty = _git_dirty(root)
    from hypercharge.grounding_session import load_grounding

    grounding = load_grounding(root)
    last_test = grounding.get("last_test") or {}
    return {
        "branch": git_branch(root),
        "dirty_files": dirty[:20],
        "dirty_count": len(dirty),
        "graph": graph_hash(root) if graph_is_present(root) else "missing",
        "loose_ends": len(ends),
        "active_threads": len(active_open_chats(root)),
        "current_chat": peek_current_chat_id(root),
        "last_test_exit": last_test.get("exit_code"),
        "read_snapshots": len((grounding.get("read_snapshots") or {})),
    }


def run_status(root: Path, console: HyperConsole, *, as_json: bool = False) -> int:
    """Run status. Args: root, console. Returns: 0. (hypercharge-managed)"""
    root = root.resolve()
    report = build_status_report(root)
    if as_json:
        print(json.dumps(report, indent=2))
        return 0
    lines = [
        f"branch: {report['branch']}",
        f"dirty: {report['dirty_count']} file(s)",
        f"graph: {report['graph']}",
        f"loose ends: {report['loose_ends']}",
        f"threads: {report['active_threads']} (current: {report['current_chat'] or 'none'})",
    ]
    if report.get("last_test_exit") is not None:
        lines.append(f"last test exit: {report['last_test_exit']}")
    if report["dirty_files"]:
        lines.append("dirty files: " + ", ".join(report["dirty_files"][:8]))
    print("\n".join(lines))
    return 0
