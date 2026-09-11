"""Hypercharge CLI — install · setup · wrapup"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from hypercharge import __version__
from hypercharge.install_cmd import run_install
from hypercharge.setup_cmd import run_setup
from hypercharge.ui.console import HyperConsole
from hypercharge.ui import copy_en_gb as copy
from hypercharge.wrapup_cmd import run_wrapup


def _add_target_arg(p: argparse.ArgumentParser) -> None:
    """Internal _add_target_arg. Args: p. (hypercharge-managed)"""
    p.add_argument(
        "--target",
        choices=("cursor", "claude", "both"),
        default="both",
        help="Agent IDE to wire: cursor, claude, or both (default: both)",
    )


def _add_start_day_args(p: argparse.ArgumentParser) -> None:
    """Internal _add_start_day_args. Args: p. (hypercharge-managed)"""
    p.add_argument("--refresh-graph", action="store_true", help="Run graphify update first")
    p.add_argument("--no-graph", action="store_true")
    p.add_argument("--json", action="store_true", help="Structured manifest for agent story")
    p.add_argument("--path", type=Path, default=Path.cwd())


def build_parser() -> argparse.ArgumentParser:
    """Build parser. Returns: p. (hypercharge-managed)"""
    p = argparse.ArgumentParser(
        prog="hypercharge",
        description="Hypercharger — intelligent repo agent for Cursor and Claude Code. Say 'install hypercharge' in chat to get started.",
    )
    p.add_argument("--plain", action="store_true", help="Plain output (no Rich)")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = p.add_subparsers(dest="command", required=True)

    ins = sub.add_parser("install", help="Once per machine")
    ins.add_argument("--org", default="yourco")
    ins.add_argument("--air-gap", action="store_true")
    _add_target_arg(ins)

    ob = sub.add_parser(
        "onboard",
        aliases=["hypercharger"],
        help="Hypercharger — install machine + setup repo (agent default)",
    )
    ob.add_argument("--org", default="yourco")
    ob.add_argument("--air-gap", action="store_true")
    ob.add_argument("--no-graph", action="store_true")
    ob.add_argument("--no-viz", action="store_true")
    ob.add_argument("--label", action="store_true")
    ob.add_argument("--compile", action="store_true", dest="compile_rules")
    ob.add_argument("--skip-machine-install", action="store_true")
    ob.add_argument("--json", action="store_true", help="Machine-readable manifest")
    ob.add_argument("--path", type=Path, default=Path.cwd())
    _add_target_arg(ob)

    setup = sub.add_parser("setup", help="Per repo — graph, inventory, rules compile")
    setup.add_argument("--org", default="yourco")
    setup.add_argument("--full", action="store_true", help="Always run interactive prompts")
    setup.add_argument("--no-graph", action="store_true")
    setup.add_argument("--no-viz", action="store_true", help="Skip graph.html and GRAPH_TREE.html")
    setup.add_argument(
        "--label",
        action="store_true",
        help="Re-name graph communities from code paths and refresh graph.html",
    )
    setup.add_argument(
        "--compile",
        action="store_true",
        dest="compile_rules",
        help="Run rules compile immediately (non-interactive)",
    )
    setup.add_argument("--skip-dialogue", action="store_true")
    setup.add_argument("--air-gap", action="store_true")
    setup.add_argument("--path", type=Path, default=Path.cwd())
    _add_target_arg(setup)

    wrap = sub.add_parser("wrapup", help="Chat or day wrapup")
    wrap.add_argument("--brief", action="store_true", help="Repo briefing (no wrapup side effects)")
    wrap.add_argument("--start-day", action="store_true", help="Morning loose-ends review")
    wrap.add_argument("--day", action="store_true", help="Day wrapup")
    wrap.add_argument("--chat", action="store_true", help="Chat wrapup (default)")
    wrap.add_argument("--archive", action="store_true", help="Archive current chat thread")
    wrap.add_argument("--defer-questions", action="store_true", help="Archive despite open questions")
    wrap.add_argument("--no-graph", action="store_true")
    wrap.add_argument("--quick", action="store_true", help="Skip graph refresh on day wrapup")
    wrap.add_argument("--refresh-graph", action="store_true", help="Refresh graph before start-day")
    wrap.add_argument("--json", action="store_true", help="JSON output (start-day)")
    wrap.add_argument("--path", type=Path, default=Path.cwd())

    q = sub.add_parser("query", help=argparse.SUPPRESS)
    q.add_argument("question", nargs="+", help="Question about the repo")
    q.add_argument("--budget", type=int, default=1500, help="Token budget for graphify query")
    q.add_argument("--air-gap", action="store_true", help="Offline install only (vendor wheels)")
    q.add_argument("--path", type=Path, default=Path.cwd())

    ctx = sub.add_parser(
        "context",
        help=argparse.SUPPRESS,
    )
    ctx.add_argument("question", nargs="+", help="Topic to ground on")
    ctx.add_argument("--budget", type=int, default=1500)
    ctx.add_argument("--air-gap", action="store_true")
    ctx.add_argument("--path", type=Path, default=Path.cwd())

    stry = sub.add_parser("story", help=argparse.SUPPRESS)
    stry.add_argument("--path", type=Path, default=Path.cwd())

    br = sub.add_parser("brief", help=argparse.SUPPRESS)
    br.add_argument("--path", type=Path, default=Path.cwd())

    nc = sub.add_parser("new-chat", help="Start or resume a chat thread")
    nc.add_argument("--goal", default="", help="What this thread is for")
    nc.add_argument("--resume", default="", help="Resume existing chat id")
    nc.add_argument("--related-to", action="append", default=[], help="Optional linked chat id(s)")
    nc.add_argument("--path", type=Path, default=Path.cwd())

    for name in ("start-day", "startday"):
        sp = sub.add_parser(name, help=argparse.SUPPRESS)
        _add_start_day_args(sp)

    aud = sub.add_parser("audit", help="Review hook audit log for this session")
    aud.add_argument("--summarise", action="store_true", default=True, help="Print warn/deny/ungrounded-writes table (default)")
    aud.add_argument("--json", action="store_true", help="Output raw summary as JSON")
    aud.add_argument("--path", type=Path, default=Path.cwd())

    st = sub.add_parser("setup-status", help=argparse.SUPPRESS)
    st.add_argument("--json", action="store_true")
    st.add_argument("--path", type=Path, default=Path.cwd())

    doc = sub.add_parser("doctor", help="Health check — rules, graph, loose ends")
    doc.add_argument("--json", action="store_true")
    doc.add_argument(
        "--tier",
        choices=("ready", "ideal", "hooks", "claude-hooks"),
        default="ready",
        help="ready=setup+contract; ideal=graph+loose ends; hooks=Cursor; claude-hooks=Claude",
    )
    doc.add_argument("--path", type=Path, default=Path.cwd())

    lg = sub.add_parser("log", help="Tier-1 session write (chat file + OPEN_CHATS)")
    lg.add_argument("--file", action="append", default=[], help="File touched (repeatable)")
    lg.add_argument("--note", default="", help="Note to append to chat log")
    lg.add_argument("--question", default="", help="Open question to add")
    lg.add_argument("--goal", default="", help="Update thread goal")
    lg.add_argument("--decision", default="", help="User-confirmed decision → REPO_SESSION ## Decisions")
    lg.add_argument("--resolve-question", default="", help="Mark open question resolved")
    lg.add_argument("--defer-question", default="", help="Remove open question (deferred)")
    lg.add_argument("--supersede", default="", help="Mark matching ## Decisions lines as superseded")
    lg.add_argument("--path", type=Path, default=Path.cwd())

    pkt = sub.add_parser(
        "context-packet",
        aliases=["contextpacket"],
        help=argparse.SUPPRESS,
    )
    pkt.add_argument("--budget", type=int, default=800, help="Approx token budget")
    pkt.add_argument("--json", action="store_true")
    pkt.add_argument("--path", type=Path, default=Path.cwd())

    cr = sub.add_parser(
        "confirm-rules-review",
        help="Optional — log that rules list was reviewed (alias: compile)",
    )
    cr.add_argument("--path", type=Path, default=Path.cwd())

    cp = sub.add_parser(
        "compile",
        help=argparse.SUPPRESS,
    )
    cp.add_argument("--path", type=Path, default=Path.cwd())
    cp.add_argument("--dry-run", action="store_true", help="Show plan only; do not write files")

    esc = sub.add_parser(
        "escalation",
        help=argparse.SUPPRESS,
    )
    esc.add_argument("--task", default="", help="Hint for subagent recommendation")
    esc.add_argument("--path", type=Path, default=Path.cwd())

    sh = sub.add_parser("shrink", help=argparse.SUPPRESS)
    sh.add_argument("--file", type=Path, default=None)
    sh.add_argument("--text", default="")
    sh.add_argument("--max-chars", type=int, default=12_000)
    sh.add_argument("--air-gap", action="store_true", help="Offline headroom install only")

    lc = sub.add_parser(
        "label-communities",
        aliases=["labelcommunities"],
        help=argparse.SUPPRESS,
    )
    lc.add_argument("--path", type=Path, default=Path.cwd())
    lc.add_argument("--digest", action="store_true", help="Show top communities for host-agent refinement")
    lc.add_argument("--apply", type=Path, default=None, help="Apply labels JSON { \"0\": \"name\", ... }")
    lc.add_argument("--force", action="store_true", help="Overwrite existing non-placeholder labels")
    lc.add_argument("--json", action="store_true")

    hk = sub.add_parser("hooks", help=argparse.SUPPRESS)
    hk.add_argument(
        "event",
        choices=(
            "session-start",
            "before-prompt",
            "pre-tool",
            "after-edit",
            "after-shell",
            "after-response",
        ),
        help="Hook event name",
    )
    hk.add_argument(
        "--format",
        choices=("cursor", "claude"),
        default="cursor",
        help="IDE hook JSON dialect (default: cursor)",
    )
    hk.add_argument("--path", type=Path, default=Path.cwd())

    kn = sub.add_parser(
        "knowledge",
        aliases=["know"],
        help=argparse.SUPPRESS,
    )
    kn.add_argument("question", nargs="+", help="Question about the repo")
    kn.add_argument("--budget", type=int, default=1500)
    kn.add_argument("--air-gap", action="store_true")
    kn.add_argument("--path", type=Path, default=Path.cwd())

    mem = sub.add_parser("memory-index", help=argparse.SUPPRESS)
    mem.add_argument("--rebuild", action="store_true")
    mem.add_argument("--search", type=str, default=None)
    mem.add_argument("--limit", type=int, default=5)
    mem.add_argument("--path", type=Path, default=Path.cwd())

    st = sub.add_parser("status", help=argparse.SUPPRESS)
    st.add_argument("--json", action="store_true")
    st.add_argument("--path", type=Path, default=Path.cwd())

    vf = sub.add_parser("verify", help=argparse.SUPPRESS)
    vf.add_argument("--claim", required=True)
    vf.add_argument("--evidence", required=True, help="path:line citation")
    vf.add_argument("--path", type=Path, default=Path.cwd())

    ds = sub.add_parser("docstrings", help="Sync Python function docstrings")
    ds.add_argument("--file", action="append", default=[], dest="files")
    ds.add_argument("--dry-run", action="store_true")
    ds.add_argument("--path", type=Path, default=Path.cwd())

    td = sub.add_parser(
        "teardown",
        aliases=["remove"],
        help="Remove all Hypercharge scaffolding from this repo",
    )
    td.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be removed without changing anything",
    )
    td.add_argument(
        "--yes",
        action="store_true",
        dest="confirm",
        help="Skip confirmation prompt",
    )
    td.add_argument("--path", type=Path, default=Path.cwd())
    _add_target_arg(td)

    mcp = sub.add_parser("mcp-server", help="Run the Hypercharge MCP server (stdio transport)")
    mcp.add_argument("--repo", default=None, help="Repo root (defaults to cwd)")

    return p


def cmd_status(root: Path, console: HyperConsole, *, as_json: bool = False) -> int:
    """Cmd status. Args: root, console. Returns: _doctor_exit_code(report, tier='ready'). (hypercharge-managed)"""
    from hypercharge.doctor_cmd import build_doctor_report, _doctor_exit_code

    report = build_doctor_report(root)
    if as_json:
        print(json.dumps(report, indent=2))
        return _doctor_exit_code(report, tier="ready")

    from hypercharge.graph import graph_is_present

    lock_report = report
    rows = [
        ("Graph", "ok" if graph_is_present(root) else "warn", str(report.get("graph_hash") or "missing")),
        ("Ready", "ok" if report.get("ready") else "warn", "yes" if report.get("ready") else "check"),
        ("Active threads", "ok", str(report["active_threads"])),
        ("Loose ends", "ok" if report["loose_ends"] == 0 else "warn", str(report["loose_ends"])),
        ("Last chat wrapup", "ok", lock_report["last_chat_wrapup"]),
        ("Last day wrapup", "ok", lock_report["last_day_wrapup"]),
    ]
    console.health_table(rows)
    return _doctor_exit_code(report, tier="ready")


def cmd_query(console: HyperConsole, question: str, root: Path, *, budget: int = 2500, air_gap: bool | None = None) -> int:
    """Cmd query. Args: console, question, root. Returns: code. (hypercharge-managed)"""
    from hypercharge.context import run_grounded_query
    from hypercharge.paths import user_air_gap

    gap = user_air_gap() if air_gap is None else air_gap
    code, text = run_grounded_query(root, question, budget=budget, console=console, air_gap=gap)
    print(text)
    if code != 0:
        console.warn(text.splitlines()[0])
    return code


def main(argv: list[str] | None = None) -> int:
    """Main. Args: argv. Returns: 0. (hypercharge-managed)"""
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)
    plain = args.plain or not sys.stdout.isatty()
    console = HyperConsole(plain=plain)

    if args.command == "install":
        return run_install(console, org=args.org, air_gap=args.air_gap, target=args.target)

    if args.command in ("onboard", "hypercharger"):
        from hypercharge.onboard_cmd import run_onboard

        return run_onboard(
            args.path,
            console,
            org=args.org,
            air_gap=args.air_gap,
            no_graph=args.no_graph,
            no_viz=args.no_viz,
            label=args.label,
            compile_rules=args.compile_rules,
            skip_machine_install=args.skip_machine_install,
            as_json=args.json,
            target=args.target,
        )

    if args.command == "setup":
        return run_setup(
            args.path,
            console,
            org=args.org,
            full=args.full,
            no_graph=args.no_graph,
            no_viz=args.no_viz,
            label=args.label,
            compile_rules=args.compile_rules,
            skip_dialogue=args.skip_dialogue,
            air_gap=args.air_gap,
            target=args.target,
        )

    if args.command == "wrapup":
        return run_wrapup(
            args.path,
            console,
            day=args.day,
            chat=args.chat,
            archive=args.archive,
            no_graph=args.no_graph,
            quick=args.quick,
            defer_questions=args.defer_questions,
            brief=args.brief,
            start_day=args.start_day,
            as_json=args.json,
            refresh_graph=args.refresh_graph,
        )

    if args.command == "audit":
        from hypercharge.audit_log import summarise_session

        summary = summarise_session(args.path.resolve())
        if getattr(args, "json", False):
            print(json.dumps(summary, indent=2))
            return 0

        uw = summary["ungrounded_writes"]
        print(f"Session audit — total entries: {summary['total']}  warns: {summary['warns']}  denies: {summary['denies']}")
        if not uw:
            print("✓ No ungrounded writes this session.")
        else:
            col_w = max(len("Tool"), max(len(e["tool"]) for e in uw))
            col_p = max(len("Path"), max(len(e.get("path") or "—") for e in uw))
            col_n = max(len("Note"), max(len((e["detail"] or "")[:60]) for e in uw))
            header = f"{'Time':<20}  {'Tool':<{col_w}}  {'Path':<{col_p}}  {'Note':<{col_n}}"
            print(header)
            print("-" * len(header))
            for e in uw:
                ts = (e.get("ts") or "")[:19].replace("T", " ")
                tool = e.get("tool") or ""
                path_val = e.get("path") or "—"
                note = (e.get("detail") or "")[:60]
                print(f"{ts:<20}  {tool:<{col_w}}  {path_val:<{col_p}}  {note:<{col_n}}")
        return 0

    if args.command == "setup-status":
        return cmd_status(args.path.resolve(), console, as_json=args.json)

    if args.command == "doctor":
        from hypercharge.doctor_cmd import run_doctor

        return run_doctor(args.path.resolve(), console, as_json=args.json, tier=args.tier)

    if args.command == "log":
        from hypercharge.log_cmd import run_log

        return run_log(
            args.path.resolve(),
            console,
            files=args.file or None,
            note=args.note,
            question=args.question,
            goal=args.goal,
            decision=args.decision,
            resolve_question=args.resolve_question,
            defer_question=args.defer_question,
            supersede=args.supersede,
        )

    if args.command in ("context-packet", "contextpacket"):
        from hypercharge.context_packet_cmd import run_context_packet

        return run_context_packet(
            args.path.resolve(),
            budget=args.budget,
            as_json=args.json,
        )

    if args.command == "confirm-rules-review":
        from hypercharge.compile_cmd import run_compile

        return run_compile(args.path.resolve(), console, dry_run=getattr(args, "dry_run", False))

    if args.command == "compile":
        from hypercharge.compile_cmd import run_compile

        return run_compile(args.path.resolve(), console, dry_run=args.dry_run)

    if args.command == "escalation":
        from hypercharge.escalation_cmd import run_escalation

        return run_escalation(args.path.resolve(), console, task_hint=args.task or "")

    if args.command == "shrink":
        from hypercharge.shrink_cmd import run_shrink

        return run_shrink(
            console,
            text=args.text,
            file=args.file,
            max_chars=args.max_chars,
            air_gap=args.air_gap or None,
        )

    if args.command in ("label-communities", "labelcommunities"):
        from hypercharge.label_communities_cmd import run_label_communities

        return run_label_communities(
            args.path.resolve(),
            console,
            digest=args.digest,
            apply_file=args.apply,
            force=args.force,
            as_json=args.json,
        )

    if args.command == "query":
        if not args.question:
            console.step_fail("Query", 'Usage: hypercharge query "your question"')
            return 1
        return cmd_query(
            console,
            " ".join(args.question),
            args.path.resolve(),
            budget=args.budget,
            air_gap=args.air_gap or None,
        )

    if args.command == "context":
        if not args.question:
            console.step_fail("Context", 'Usage: hypercharge context "topic"')
            return 1
        return cmd_query(
            console,
            " ".join(args.question),
            args.path.resolve(),
            budget=args.budget,
            air_gap=args.air_gap or None,
        )

    if args.command == "story":
        from hypercharge.onboard_cmd import agent_story_from_manifest

        print(agent_story_from_manifest(args.path.resolve()))
        return 0

    if args.command == "brief":
        return run_wrapup(args.path.resolve(), console, brief=True)

    if args.command == "new-chat":
        from hypercharge.new_chat_cmd import run_new_chat

        return run_new_chat(
            args.path.resolve(),
            console,
            goal=args.goal,
            related_to=args.related_to or None,
            resume=args.resume or None,
        )

    if args.command in ("start-day", "startday"):
        from hypercharge.loose_ends import collect_loose_ends

        root = args.path.resolve()
        refresh = args.refresh_graph
        if not refresh and not args.no_graph:
            refresh = any(e.kind == "graph" for e in collect_loose_ends(root))
        return run_wrapup(
            root,
            console,
            start_day=True,
            refresh_graph=refresh,
            no_graph=args.no_graph,
            as_json=args.json,
        )

    if args.command == "hooks":
        from hypercharge.hooks_cmd import run_hook

        return run_hook(args.event, args.path.resolve(), hook_format=args.format)

    if args.command in ("knowledge", "know"):
        from hypercharge.knowledge_cmd import run_knowledge_query

        code, text = run_knowledge_query(
            args.path.resolve(),
            " ".join(args.question),
            budget=args.budget,
            air_gap=args.air_gap or False,
        )
        print(text)
        return code

    if args.command == "memory-index":
        from hypercharge.memory_index_cmd import run_memory_index

        return run_memory_index(
            args.path.resolve(),
            console,
            rebuild=args.rebuild,
            search=args.search,
            limit=args.limit,
        )

    if args.command == "status":
        return run_wrapup(args.path.resolve(), console, brief=True)


    if args.command == "verify":
        from hypercharge.verify_cmd import run_verify

        return run_verify(args.path.resolve(), claim=args.claim, evidence=args.evidence)

    if args.command == "docstrings":
        from hypercharge.docstrings_sync import run_docstrings

        return run_docstrings(args.path.resolve(), files=args.files or None, dry_run=args.dry_run)

    if args.command in ("teardown", "remove"):
        from hypercharge.teardown_cmd import run_teardown

        return run_teardown(
            args.path.resolve(),
            console,
            dry_run=args.dry_run,
            confirm=args.confirm,
            target=args.target,
        )

    if args.command == "mcp-server":
        import os
        from hypercharge.mcp_server import main as _mcp_main

        if args.repo:
            os.environ["HYPERCHARGE_REPO_ROOT"] = str(Path(args.repo).resolve())
        _mcp_main()
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
