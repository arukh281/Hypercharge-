"""CLI for semantic memory index."""

from __future__ import annotations

from pathlib import Path

from hypercharge.memory_index import format_memory_hits, rebuild_memory_index, search_memory_index
from hypercharge.ui.console import HyperConsole


def run_memory_index(
    root: Path,
    console: HyperConsole,
    *,
    rebuild: bool = False,
    search: str | None = None,
    limit: int = 5,
) -> int:
    root = root.resolve()
    if rebuild:
        count = rebuild_memory_index(root)
        console.step_ok("Memory index", f"Indexed {count} chunk(s)")
    if search:
        hits = search_memory_index(root, search, limit=limit)
        if not hits:
            print("No memory hits.")
            return 1
        print("## Memory hits")
        for line in format_memory_hits(hits):
            print(line)
        return 0
    if rebuild:
        return 0
    console.warn("Use --rebuild and/or --search <query>")
    return 1
