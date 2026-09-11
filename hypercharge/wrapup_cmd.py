"""Wrapup — chat and day modes."""

from __future__ import annotations

from pathlib import Path

import yaml

from hypercharge.graph import graph_hash, graph_json_path, run_graphify_build
from hypercharge.inventory import load_repo_profile
from hypercharge.paths import git_branch, git_last_commit_ts
from hypercharge.session import (
    _utc_now,
    append_repo_session,
    chats_active_today,
    ensure_session_layout,
    get_open_chat_entry,
    load_lock,
    load_open_chats,
    peek_current_chat_id,
    register_new_chat,
    save_lock,
    save_open_chats,
    upsert_open_chat,
    write_chat_wrapup_summary,
    write_day_wrapup_summary,
)
from hypercharge.session_io import chat_file_excerpt
from hypercharge.ui.console import HyperConsole


def _is_experiment(root: Path) -> bool:
    """True only for explicit personal/exploratory intent — not every feature branch."""
    intent_path = root / ".cursor/repo-intent.yaml"
    if not intent_path.is_file():
        return False
    data = yaml.safe_load(intent_path.read_text(encoding="utf-8")) or {}
    branch = git_branch(root)
    branch_overlay = (data.get("branches") or {}).get(branch, {})
    role = branch_overlay.get("role", data.get("role", ""))
    maturity = branch_overlay.get("maturity", data.get("maturity", ""))
    return role in ("personal_research", "experiment") or maturity == "exploratory"


def _flush_chat(root: Path, chat_id: str, archive: bool) -> dict:
    """Internal _flush_chat. Args: root, chat_id, archive. Returns: entry. (hypercharge-managed)"""
    branch = git_branch(root)
    chat_file = root / ".cursor/session/chats" / f"{chat_id}.md"
    existing = get_open_chat_entry(root, chat_id)

    goal = existing.get("goal", "")
    if not goal and chat_file.is_file():
        for line in chat_file.read_text(encoding="utf-8").splitlines():
            lower = line.lower().strip()
            if lower.startswith("goal:"):
                goal = line.split(":", 1)[1].strip()
            elif lower.startswith("## ") and goal in ("", "Active work"):
                heading = line[3:].strip()
                if heading.lower() not in ("chat notes (recent)", "open questions", "files touched"):
                    goal = heading

    entry: dict = {
        "id": chat_id,
        "branch": existing.get("branch") or branch,
        "goal": goal or "Active work",
        "open_questions": list(existing.get("open_questions") or []),
        "files_touched": list(existing.get("files_touched") or []),
        "status": "archived" if archive else existing.get("status", "active"),
    }
    for key in ("related_to", "blocked_on", "started"):
        if key in existing:
            entry[key] = existing[key]

    if archive:
        archive_dir = root / ".cursor/session/archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        if chat_file.is_file():
            dest = archive_dir / f"{chat_id}.md"
            dest.write_text(chat_file.read_text(encoding="utf-8"), encoding="utf-8")
            chat_file.unlink()
        data = load_open_chats(root)
        data["open"] = [x for x in data.get("open", []) if x.get("id") != chat_id]
        save_open_chats(root, data)
    else:
        upsert_open_chat(root, entry)

    return entry



def run_wrapup(
    root: Path,
    console: HyperConsole,
    *,
    day: bool = False,
    chat: bool = False,
    archive: bool = False,
    no_graph: bool = False,
    quick: bool = False,
    defer_questions: bool = False,
    brief: bool = False,
    start_day: bool = False,
    as_json: bool = False,
    refresh_graph: bool = False,
) -> int:
    """Run wrapup. Args: root, console. Returns: 0. (hypercharge-managed)"""
    root = root.resolve()

    if brief:
        from hypercharge.brief_cmd import build_brief_text

        print(build_brief_text(root))
        return 0 if (root / ".cursor").is_dir() else 1

    if start_day:
        from hypercharge.loose_ends import collect_loose_ends
        from hypercharge.start_day_cmd import run_start_day

        if not refresh_graph and not no_graph:
            refresh_graph = any(e.kind == "graph" for e in collect_loose_ends(root))
        return run_start_day(
            root,
            console,
            refresh_graph=refresh_graph,
            no_graph=no_graph,
            as_json=as_json,
        )

    if not (root / ".cursor").is_dir():
        console.step_fail("Wrapup", "Run hypercharge setup in this repo first.")
        return 1

    ensure_session_layout(root)
    mode = "day" if day else "chat"
    if day:
        chat = True

    experiment = _is_experiment(root)
    chat_id = peek_current_chat_id(root)
    if not chat_id:
        chat_id = register_new_chat(root, goal="Active work")
        console.warn("No CURRENT_CHAT — created default thread for wrapup.")
    branch = git_branch(root)

    existing = get_open_chat_entry(root, chat_id)
    if archive and not day and existing.get("open_questions") and not defer_questions:
        qs = existing.get("open_questions") or []
        console.step_fail(
            "Wrapup",
            f"{len(qs)} open question(s) — resolve in start-day or pass --defer-questions",
        )
        return 1

    excerpt = chat_file_excerpt(root, chat_id)
    entry = _flush_chat(root, chat_id, archive=archive and not day)

    if not experiment:
        summary_bit = f"Chat wrapup ({chat_id}): {entry.get('goal', 'Active work')}"
        if entry.get("open_questions"):
            summary_bit += f" [{len(entry['open_questions'])} open]"
        append_repo_session(root, summary_bit, branch=branch, experiment=False)

    summary_lines = [
        f"# Wrapup {mode}",
        f"Time: {_utc_now()}",
        f"Chat: {chat_id}",
        f"Goal: {entry.get('goal', '—')}",
        f"Branch: {branch}",
        f"Experiment gate: {'yes' if experiment else 'no'}",
        "",
    ]
    if excerpt:
        summary_lines.append("## Chat notes (recent)")
        summary_lines.extend(excerpt)
        summary_lines.append("")
    if entry.get("open_questions"):
        summary_lines.append("## Open questions")
        summary_lines.extend(f"- {q}" for q in entry["open_questions"])
        summary_lines.append("")
    if entry.get("files_touched"):
        summary_lines.append("## Files touched")
        summary_lines.extend(f"- {f}" for f in entry["files_touched"][:20])
        summary_lines.append("")

    write_chat_wrapup_summary(root, chat_id, "\n".join(summary_lines))

    # Warn if graph predates the last commit regardless of mode.
    if not no_graph:
        gp = graph_json_path(root)
        commit_ts = git_last_commit_ts(root)
        if gp.is_file() and commit_ts is not None and gp.stat().st_mtime < commit_ts:
            console.warn(
                "Graph predates last git commit — structural claims may be wrong. "
                "Run `hypercharge wrapup --day` or `graphify update .` to refresh."
            )

    graph_updated = False
    if day and not no_graph and not quick:
        ok, msg = run_graphify_build(root, update=True, export_viz=True)
        if ok:
            graph_updated = True
        else:
            console.warn(f"Graph update: {msg}")
        # A full rebuild subsumes any queued incremental refresh.
        from hypercharge.graph_refresh import clear_queue

        clear_queue(root)
    elif not day and not no_graph and not quick:
        # Chat wrapup drains the refresh queue the after-edit hook fills — this is
        # where "refresh is queued for wrapup" actually happens, off the hot path.
        from hypercharge.graph_refresh import drain_if_ready

        drain_if_ready(root, debounce_sec=0)

    lock = load_lock(root)
    lock["last_chat_wrapup"] = _utc_now()
    if day:
        lock["last_day_wrapup"] = _utc_now()
        lock["graph_hash"] = graph_hash(root)
        chats = chats_active_today(root)
        if not experiment and chats:
            for c in chats:
                cid = c.get("id", "?")
                goal = c.get("goal", "")
                qs = c.get("open_questions") or []
                line = f"Day roll-up {cid}: {goal}"
                if qs:
                    line += f" (open: {len(qs)})"
                append_repo_session(root, line, branch=branch, experiment=False)
        body = "\n".join(
            summary_lines
            + [f"Chats today: {len(chats)}", f"Graph updated: {graph_updated}"]
        )
        write_day_wrapup_summary(root, body)
        held = ["prefs", "README"] if experiment else []
        console.wrapup_day_panel(len(chats), graph_updated, held)
    else:
        console.wrapup_chat_panel(chat_id, archive, len(entry.get("open_questions", [])), experiment)

    save_lock(root, lock)

    from hypercharge.memory_index import rebuild_memory_index

    try:
        indexed = rebuild_memory_index(root)
        if indexed and day:
            console.warn(f"Memory index: {indexed} chunk(s) indexed")
    except OSError:
        pass

    if archive and not day:
        register_new_chat(root, goal="New thread")

    return 0
