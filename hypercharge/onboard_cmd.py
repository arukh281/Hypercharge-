"""One-shot Hypercharger onboard — install machine + wire repo (agent-driven)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from hypercharge import __version__
from hypercharge.graph import (
    graph_artifacts_summary,
    graph_hash,
    graph_html_path,
    graph_is_present,
    graph_json_path,
    graph_node_count,
    graph_report_path,
    graph_tree_path,
)
from hypercharge.install_cmd import run_install
from hypercharge.paths import (
    CURSOR_HYPERCHARGE,
    ensure_hypercharge_venv,
    find_git_root,
    resolve_hypercharge_source,
)
from hypercharge.setup_cmd import run_setup
from hypercharge.ui import copy_en_gb as copy
from hypercharge.ui.console import HyperConsole


_PANEL_SEP = "━" * 42


def _graph_stats(root: Path) -> str:
    """Return 'N nodes, M edges' from graph.json, or 'graph building...' if absent."""
    gj = graph_json_path(root)
    if not gj.is_file():
        return "graph building..."
    try:
        data = json.loads(gj.read_text(encoding="utf-8"))
        nodes_val = data.get("nodes")
        edges_val = data.get("edges")
        n = len(nodes_val) if isinstance(nodes_val, list) else (nodes_val if isinstance(nodes_val, int) else "?")
        e = len(edges_val) if isinstance(edges_val, list) else (edges_val if isinstance(edges_val, int) else "?")
        return f"{n} nodes, {e} edges"
    except (json.JSONDecodeError, OSError):
        return "graph building..."


def _print_ready_panel(root: Path) -> None:
    """Print the post-onboard summary panel to stdout."""
    stats = _graph_stats(root)
    print(f"\n{_PANEL_SEP}")
    print("  Hypercharger ready")
    print(_PANEL_SEP)
    print()
    print("  What to say in your first chat:")
    print('  \u2022 "What\'s going on?" \u2014 get a briefing')
    print('  \u2022 "Fix the [bug name]" \u2014 agent looks up code and edits')
    print('  \u2022 "New topic \u2014 [goal]" \u2014 start a focused thread')
    print('  \u2022 "Wrap up" \u2014 save this session')
    print()
    print("  Health:  hypercharge doctor --tier ready")
    print(f"  Graph:   {stats}")
    print("  Memory:  hypercharge wrapup --day  (rebuilds nightly)")
    print(f"{_PANEL_SEP}\n")


def _write_onboard_manifest(root: Path, *, phases: dict) -> Path:
    """Internal _write_onboard_manifest. Args: root. Returns: path. (hypercharge-managed)"""
    root = root.resolve()
    out_dir = root / CURSOR_HYPERCHARGE
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "hypercharger_version": __version__,
        "status": "ready",
        "repo_root": str(root),
        "phases": phases,
        "graph": {
            "present": graph_is_present(root),
            "hash": graph_hash(root),
            "nodes": graph_node_count(root),
            "status": "ok" if graph_is_present(root) else "degraded",
        },
        "artifacts": {
            "graph_html": str(graph_html_path(root).relative_to(root)),
            "tree_html": str(graph_tree_path(root).relative_to(root)),
            "graph_json": str(graph_json_path(root).relative_to(root)),
            "report": str(graph_report_path(root).relative_to(root)),
        },
        "pending_user_steps": [],
        "agent_must_ask": [],
        "presentation": "story_not_logs",
    }
    path = out_dir / "last-onboard.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return path


def run_onboard(
    start: Path,
    console: HyperConsole,
    *,
    org: str = "yourco",
    air_gap: bool = False,
    no_graph: bool = False,
    no_viz: bool = False,
    label: bool = False,
    compile_rules: bool = False,
    skip_machine_install: bool = False,
    as_json: bool = False,
    target: str = "both",
) -> int:
    """Install Hypercharge on the machine, then set up the git repo — one flow."""
    start = start.resolve()
    if as_json:

        class _NullConsole:
            plain = True

            def banner(self):
                """Banner. Returns: None. (hypercharge-managed)"""
                return None

            def step_ok(self, *_a, **_k):
                """Step ok. Returns: None. (hypercharge-managed)"""
                return None

            def step_fail(self, *_a, **_k):
                """Step fail. Returns: None. (hypercharge-managed)"""
                return None

            def warn(self, *_a, **_k):
                """Warn. Returns: None. (hypercharge-managed)"""
                return None

            def footer(self, *_a, **_k):
                """Footer. Returns: None. (hypercharge-managed)"""
                return None

            def inventory_table(self, *_a, **_k):
                """Inventory table. Returns: None. (hypercharge-managed)"""
                return None

            def health_table(self, *_a, **_k):
                """Health table. Returns: None. (hypercharge-managed)"""
                return None

        console = _NullConsole()

    elif not as_json:
        console.banner()

    phases: dict[str, str] = {}
    hc_root = resolve_hypercharge_source(start)

    # --- Phase 1: machine ---
    if not skip_machine_install:
        if not as_json:
            console.step_ok(f"Hypercharge source: {hc_root}", 1, 3)
        try:
            venv_python = ensure_hypercharge_venv(hc_root)
            phases["venv"] = str(venv_python)
        except (OSError, subprocess.CalledProcessError) as exc:
            if as_json:
                print(json.dumps({"status": "machine_install_failed", "error": str(exc)}))
            else:
                console.step_fail("Machine install", str(exc))
            return 1

        code = run_install(
            console, org=org, air_gap=air_gap, hc_root=hc_root, quiet=as_json, target=target
        )
        if code != 0:
            return code
        phases["machine"] = "installed"
    else:
        phases["machine"] = "skipped"

    # --- Phase 2: repo root ---
    git_root = find_git_root(start)
    if git_root is None:
        console.warn("Not inside a git repo — machine install only.")
        console.footer(
            "Hypercharger (machine only)",
            [
                "CLI + skill installed.",
                "Open a project folder in chat and say **install hypercharge** again — I'll wire the repo.",
            ],
        )
        phases["repo"] = "skipped_no_git"
        if as_json:
            print(json.dumps({"status": "machine_only", "phases": phases}, indent=2))
        return 0

    phases["repo_root"] = str(git_root)

    # --- Phase 3: repo setup ---
    setup_code = run_setup(
        git_root,
        console,
        org=org,
        no_graph=no_graph,
        no_viz=no_viz,
        label=label,
        compile_rules=compile_rules,
        skip_dialogue=True,
        air_gap=air_gap,
        quiet=as_json,
        target=target,
    )
    if setup_code != 0:
        phases["repo"] = "setup_failed"
        return setup_code

    if not graph_is_present(git_root):
        phases["graph_status"] = "degraded"
    else:
        phases["graph_status"] = "ok"

    if not compile_rules:
        pass  # rules compile optional via hypercharge compile

    phases["repo"] = "setup_ok"
    from hypercharge.runtime_paths import write_runtime_manifest

    write_runtime_manifest(git_root, hc_root=hc_root)
    phases["runtime_manifest"] = ".cursor/hypercharge/runtime.json"

    from hypercharge.doctor_cmd import build_doctor_report, _doctor_exit_code

    doctor_report = build_doctor_report(git_root)
    ready_ok = _doctor_exit_code(doctor_report, tier="ready") == 0
    phases["doctor_ready"] = "ok" if ready_ok else "failed"
    if not ready_ok:
        phases["doctor_issues"] = doctor_report.get("hooks_issues") or []
        if not as_json:
            console.warn(
                "Doctor --tier ready failed: "
                + ", ".join(phases["doctor_issues"][:4])
                + " — re-run hypercharge setup."
            )
        if as_json:
            print(json.dumps({"status": "doctor_not_ready", "phases": phases}, indent=2))
        return 1

    manifest_path = _write_onboard_manifest(git_root, phases=phases)

    footer = [
        "Hypercharger is ready for this repo.",
        f"Manifest: {manifest_path.relative_to(git_root)}",
        *graph_artifacts_summary(git_root),
        copy.NEXT_COMPILE,
        copy.NEXT_WRAPUP_CHAT,
    ]

    if as_json:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        print(json.dumps(data, indent=2))
    else:
        console.footer("Hypercharger ready", footer)
        _print_ready_panel(git_root)

    return 0


def agent_story_from_manifest(root: Path) -> str:
    """Plain story for agents to paste after onboard (reads last-onboard.json)."""
    path = root / CURSOR_HYPERCHARGE / "last-onboard.json"
    if not path.is_file():
        return copy.AGENT_REPLY_AFTER_INSTALL.strip()
    data = json.loads(path.read_text(encoding="utf-8"))
    graph = data.get("graph") or {}
    graph_status = graph.get("status", "ok")
    nodes = graph.get("nodes") or "?"
    lines = [
        "**Done — Hypercharger is ready.**",
        "",
        f"- **Repo:** `{data.get('repo_root', root)}`",
    ]
    if graph_status == "degraded":
        lines.append("- **Code map:** degraded — grounding is UNVERIFIED until graph builds.")
        lines.append("- **Next:** say **wrap up --day** or re-run setup when graphify is available.")
    else:
        lines.append(f"- **Code map:** {nodes} nodes — ask me structure questions any time.")
        lines.append(
            f"- **Browser:** `{graph_html_path(root).relative_to(root)}` + "
            f"`{graph_tree_path(root).relative_to(root)}`"
        )
    lines.extend([
        "- **Session:** `.cursor/session/` — say **wrap up** when this chat ends.",
        "- **Health:** `hypercharge doctor --tier ready` after setup.",
        "- **Your rules:** not changed.",
        "",
    ])
    if data.get("agent_must_ask"):
        lines.append("**One question:** run **rules compile**? (logs review — almost never edits files)")
    return "\n".join(lines)
