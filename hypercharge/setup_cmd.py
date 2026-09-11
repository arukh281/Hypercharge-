"""Setup command."""

from __future__ import annotations

import sys
from pathlib import Path

from hypercharge import __version__
from hypercharge.graph import (
    ensure_graphify,
    ensure_graphify_layout,
    graph_artifacts_summary,
    graph_hash,
    graph_is_present,
    run_graphify_build,
    validate_setup_root,
)
from hypercharge.intent_propose import propose_intent, write_repo_intent
from hypercharge.inventory import (
    load_repo_profile,
    save_repo_profile,
    scan_project_inventory,
    scan_user_skills,
    write_inventory_report,
    inventory_user_summary,
)
from hypercharge.session import ensure_session_layout
from hypercharge.skill_packs import sync_bundled_skills
from hypercharge.templates_deploy import MANAGED_RULES, deploy_templates
from hypercharge.ui import copy_en_gb as copy
from hypercharge.ui.console import HyperConsole


def run_setup(
    root: Path,
    console: HyperConsole,
    *,
    org: str = "yourco",
    quick: bool = True,
    full: bool = False,
    no_graph: bool = False,
    no_viz: bool = False,
    label: bool = False,
    compile_rules: bool = False,
    skip_dialogue: bool = False,
    air_gap: bool = False,
    target: str = "both",
    quiet: bool = False,
) -> int:
    """Run setup. Args: root, console. Returns: 0. (hypercharge-managed)"""
    root = root.resolve()
    if full:
        skip_dialogue = False
    if not quiet:
        console.banner()

    for w in validate_setup_root(root):
        console.warn(w)
        if sys.stdin.isatty() and not skip_dialogue:
            ans = input("Continue setup in this directory anyway? [y/N]: ").strip().lower()
            if ans not in ("y", "yes"):
                console.footer("Setup cancelled", ["cd your-repo && hypercharge setup"])
                return 1

    total = 6

    # 1 Migrate — graphify layout + legacy path move
    from hypercharge.graph import migrate_legacy_graphify_out

    migrated = migrate_legacy_graphify_out(root)
    ensure_graphify_layout(root)
    migrate_msg = "graphify → .cursor/graphify-out" if migrated else "layout ok"
    console.step_ok(f"Migrate ({migrate_msg})", 1, total)

    # 2 Templates + global skills refresh
    ensure_session_layout(root)
    created = deploy_templates(root, org=org, target=target)
    ensure_graphify_layout(root)
    skill_count, _ = sync_bundled_skills(target=target)
    synced = sum(1 for p in created if p.endswith(".mdc") and not p.startswith("(removed)"))
    console.step_ok(
        f"Rules synced ({synced}) + templates ({len(created)} touched) + skills ({skill_count})",
        2,
        total,
    )

    # 3 Graph
    if no_graph:
        console.warn("Graph skipped (--no-graph). Grounding uses UNVERIFIED protocol.")
        console.step_ok("Graph (skipped)", 3, total)
    else:
        if not ensure_graphify(console, air_gap=air_gap):
            if skip_dialogue or not sys.stdin.isatty():
                console.warn("Graphify not available — continuing degraded (UNVERIFIED grounding).")
                console.step_ok("Graphify (degraded)", 3, total)
            else:
                console.step_fail("Graphify", "Install graphify or re-run with --no-graph")
                return 1
        else:
            with console.spinner("Building graph (code/AST)") as progress:
                if progress and hasattr(progress, "add_task"):
                    progress.add_task("graphify", total=None)
                ok, msg = run_graphify_build(
                    root,
                    update=True,
                    export_viz=not no_viz,
                    label_communities=label,
                    air_gap=air_gap,
                )
            if ok:
                detail = graph_hash(root) or msg
                if not no_viz:
                    detail += " + browser exports"
                console.step_ok(f"Graph ({detail})", 3, total)
                if not graph_is_present(root):
                    console.warn("For doc/paper semantics, run graphify in this chat (no API key export).")
            else:
                console.step_fail("Graph", msg)
                if sys.stdin.isatty() and not skip_dialogue:
                    ans = input("Continue without graph? [Y/n]: ").strip().lower()
                    if ans == "n":
                        return 1
                    console.warn("Continuing without graph — grounding stays UNVERIFIED.")
                    console.step_ok("Graph (skipped after failure)", 3, total)
                else:
                    console.warn("Graph build failed — continuing degraded (UNVERIFIED grounding).")
                    console.step_ok("Graph (degraded)", 3, total)

    # 4 Intent
    intent_path = root / ".cursor/repo-intent.yaml"
    intent = propose_intent(root)
    if not skip_dialogue and sys.stdin.isatty():
        console.console.print("\n[bold]Intent proposal[/] (edit `.cursor/repo-intent.yaml` later)\n")
        for k, v in intent.items():
            if k not in ("branches", "paths") and not isinstance(v, dict):
                console.console.print(f"  {k}: {v}")
        ans = input("\nAccept intent proposal? [Y/n]: ").strip().lower()
        if ans == "n":
            console.warn("Intent not written — edit manually later.")
        else:
            write_repo_intent(root, intent)
    elif not intent_path.is_file():
        write_repo_intent(root, intent)
    console.step_ok("Intent", 4, total)

    # 5 Inventory
    project_rows = scan_project_inventory(root)
    user_rows = scan_user_skills()
    all_rows = project_rows + user_rows
    write_inventory_report(root, all_rows)
    console.inventory_table(all_rows[:40])
    console.step_ok(f"Inventory ({len(all_rows)} items)", 5, total)

    # 6 Optional rules compile (Cursor-only — Claude uses CLAUDE.md contract)
    compile_done = False
    from hypercharge.agent_target import deploys_cursor, normalize_agent_target

    target = normalize_agent_target(target)
    if not deploys_cursor(target):
        console.step_ok("Rules compile (skipped — Claude target)", 6, total)
    elif compile_rules:
        from hypercharge.compile_cmd import run_confirm_rules_review

        run_confirm_rules_review(root)
        compile_done = True
        console.step_ok("Rules compile", 6, total)
    else:
        console.step_ok("Rules compile (optional — hypercharge compile)", 6, total)

    profile = load_repo_profile(root) or {}
    profile.setdefault("hypercharge_version", __version__)
    profile.setdefault("org", org)
    profile.setdefault("locale", "en-GB")
    profile.setdefault("graph", {})
    if isinstance(profile["graph"], dict):
        profile["graph"]["extraction_mode"] = "host_agent"
    save_repo_profile(root, profile)

    from hypercharge.runtime_paths import write_runtime_manifest

    write_runtime_manifest(root)

    try:
        from hypercharge.memory_index import rebuild_memory_index

        rebuild_memory_index(root)
    except OSError:
        pass

    footer_lines = list(
        copy.SETUP_FOOTER_RULES_REVIEW_DONE if compile_done else copy.SETUP_FOOTER_READY
    )
    if not compile_done:
        synced = " + ".join(f"{name}" for name in MANAGED_RULES)
        for i, line in enumerate(footer_lines):
            if line.startswith("Synced:"):
                footer_lines[i] = f"Synced: {synced} (always apply)."
                break
    footer_lines.extend(graph_artifacts_summary(root))
    if not compile_done:
        footer_lines.append(copy.NEXT_COMPILE)
    footer_lines.extend(inventory_user_summary(all_rows))
    if not quiet:
        console.footer("Setup complete", footer_lines)
    return 0
