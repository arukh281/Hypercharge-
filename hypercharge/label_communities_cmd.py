"""CLI: name graph communities without external API keys."""

from __future__ import annotations

import json
from pathlib import Path

from hypercharge.community_labels import (
    community_digest,
    labels_path,
    load_labels,
    name_communities_for_host_agent,
    refresh_graph_viz,
    write_labels,
)
from hypercharge.graph import graph_is_present
from hypercharge.ui.console import HyperConsole


def run_label_communities(
    root: Path,
    console: HyperConsole,
    *,
    digest: bool = False,
    apply_file: Path | None = None,
    force: bool = False,
    as_json: bool = False,
) -> int:
    root = root.resolve()
    if not graph_is_present(root):
        console.step_fail("Label communities", "No code map — run hypercharge setup or wrapup --day first.")
        return 1

    if digest:
        data = {"communities": community_digest(root)}
        if as_json:
            print(json.dumps(data, indent=2))
        else:
            for row in data["communities"]:
                print(
                    f"- {row['community']}: {row['heuristic_name']} "
                    f"({row['nodes_hint']} paths) e.g. {row['sample_paths'][:2]}"
                )
        return 0

    if apply_file is not None:
        if not apply_file.is_file():
            console.step_fail("Label communities", f"File not found: {apply_file}")
            return 1
        raw = json.loads(apply_file.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and "labels" in raw:
            raw = raw["labels"]
        labels = {int(k): str(v) for k, v in raw.items()}
        write_labels(root, labels)
        ok, msg = refresh_graph_viz(root)
        if not ok:
            console.step_fail("Label communities", msg)
            return 1
        console.footer("Communities labelled", [f"Applied {len(labels)} names", msg])
        return 0

    ok, msg, labels = name_communities_for_host_agent(root, force=force)
    if as_json:
        print(json.dumps({"ok": ok, "message": msg, "count": len(labels), "sample": dict(list(labels.items())[:12])}, indent=2))
        return 0 if ok else 1

    if not ok:
        console.step_fail("Label communities", msg)
        return 1

    existing = load_labels(root)
    console.footer(
        "Communities labelled",
        [msg, f"Labels file: {labels_path(root).relative_to(root)} ({len(existing)} communities)"],
    )
    return 0
