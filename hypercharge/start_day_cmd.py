"""Start day — loose ends review and morning orientation."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from hypercharge.graph import graph_hash, run_graphify_build
from hypercharge.loose_ends import build_start_day_text, collect_loose_ends
from hypercharge.paths import CURSOR_SESSION
from hypercharge.session import ensure_session_layout
from hypercharge.ui.console import HyperConsole


def _append_start_day_log(root: Path, body: str) -> None:
    log = root / CURSOR_SESSION / "START_DAY_LOG.md"
    log.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    entry = f"\n## {stamp}\n\n{body.strip()}\n"
    if log.is_file():
        log.write_text(log.read_text(encoding="utf-8") + entry, encoding="utf-8")
    else:
        log.write_text(f"# Start day log\n{entry}", encoding="utf-8")


def run_start_day(
    root: Path,
    console: HyperConsole,
    *,
    refresh_graph: bool = False,
    no_graph: bool = False,
    as_json: bool = False,
) -> int:
    root = root.resolve()
    if not (root / ".cursor").is_dir():
        console.step_fail("Start day", "Run hypercharge setup in this repo first.")
        return 1

    ensure_session_layout(root)

    if refresh_graph and not no_graph:
        ok, msg = run_graphify_build(root, update=True)
        if ok:
            console.step_ok(f"Graph refreshed ({graph_hash(root) or msg})", 1, 1)
        else:
            console.warn(f"Graph refresh skipped: {msg}")

    if as_json:
        import json

        from hypercharge.loose_ends import build_start_day_payload

        print(json.dumps(build_start_day_payload(root), indent=2))
    else:
        text = build_start_day_text(root)
        print(text)

    ends = collect_loose_ends(root)
    summary = f"Loose ends: {len(ends)}"
    if ends:
        summary += " — " + ", ".join(e.id for e in ends[:8])
        if len(ends) > 8:
            summary += " …"
    _append_start_day_log(root, summary)

    return 0
