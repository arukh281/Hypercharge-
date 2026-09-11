"""Name graph communities without external API keys — path heuristics + host-agent refresh."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from hypercharge.graph import graph_json_path, graphify_cmd, graph_is_present, graphify_out_dir

_PLACEHOLDER = re.compile(r"^Community \d+$", re.IGNORECASE)
_SKIP_PARTS = frozenset(
    {"src", "lib", "tests", "test", "docs", "scripts", "node_modules", "__pycache__"}
)


def labels_path(root: Path) -> Path:
    return graphify_out_dir(root) / ".graphify_labels.json"


def load_labels(root: Path) -> dict[int, str]:
    path = labels_path(root)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {int(k): str(v) for k, v in raw.items()}
    except (json.JSONDecodeError, OSError, ValueError):
        return {}


def labels_are_placeholder(labels: dict[int, str]) -> bool:
    if not labels:
        return True
    return all(_PLACEHOLDER.match(str(v).strip()) for v in labels.values())


def collect_community_paths(root: Path) -> dict[int, list[str]]:
    """Group source_file paths by community id from graph.json."""
    path = graph_json_path(root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    by_comm: dict[int, list[str]] = {}
    for node in data.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        cid_raw = node.get("community")
        if cid_raw is None:
            continue
        try:
            cid = int(cid_raw)
        except (TypeError, ValueError):
            continue
        src = node.get("source_file") or ""
        if src:
            by_comm.setdefault(cid, []).append(str(src))
    return by_comm


def _heuristic_name(paths: list[str]) -> str:
    if not paths:
        return "misc"

    tops = Counter()
    pairs: Counter[tuple[str, str]] = Counter()
    stems: Counter[str] = Counter()

    for raw in paths:
        parts = Path(raw).parts
        if not parts:
            continue
        tops[parts[0]] += 1
        if len(parts) >= 2:
            pairs[(parts[0], parts[1])] += 1
        stems[Path(raw).stem] += 1

    if pairs:
        (a, b), n = pairs.most_common(1)[0]
        if n >= max(2, len(paths) // 4):
            if b.lower() not in _SKIP_PARTS:
                return f"{a} · {b}"
            return a

    if tops:
        owner, n = tops.most_common(1)[0]
        if n >= len(paths) // 3:
            return owner

    if stems:
        stem, _ = stems.most_common(1)[0]
        return stem.replace("_", " ")[:48]

    return Path(paths[0]).parent.name or "misc"


def build_heuristic_labels(root: Path) -> dict[int, str]:
    by_comm = collect_community_paths(root)
    return {cid: _heuristic_name(paths) for cid, paths in by_comm.items()}


def write_labels(root: Path, labels: dict[int, str]) -> Path:
    out = labels_path(root)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {str(k): v for k, v in sorted(labels.items())}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def refresh_graph_viz(root: Path, hc_root: Path | None = None) -> tuple[bool, str]:
    """Re-export graph.html so community names appear in the browser map."""
    import subprocess

    from hypercharge.graph import _graphify_env

    root = root.resolve()
    cmd = [*graphify_cmd(hc_root), "export", "html"]
    try:
        proc = subprocess.run(
            cmd,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=900,
            env=_graphify_env(root),
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "export html failed").strip()
            return False, err
        return True, "graph.html refreshed"
    except FileNotFoundError:
        return False, "graphify not found"
    except subprocess.TimeoutExpired:
        return False, "graphify export html timed out"


def name_communities_for_host_agent(
    root: Path,
    *,
    hc_root: Path | None = None,
    force: bool = False,
) -> tuple[bool, str, dict[int, str]]:
    """
    Name communities using path heuristics (no API key), then refresh graph.html.

    The Cursor/Claude host agent can refine names later via `hypercharge label-communities`.
    """
    root = root.resolve()
    if not graph_is_present(root):
        return False, "no graph.json", {}

    existing = load_labels(root)
    if existing and not labels_are_placeholder(existing) and not force:
        return True, "community labels kept", existing

    labels = build_heuristic_labels(root)
    if not labels:
        return False, "no communities in graph", {}

    write_labels(root, labels)
    ok, msg = refresh_graph_viz(root, hc_root=hc_root)
    if not ok:
        return False, f"labels written but {msg}", labels

    sample = ", ".join(list(labels.values())[:4])
    if len(labels) > 4:
        sample += f" (+{len(labels) - 4} more)"
    return True, f"communities named from code paths ({len(labels)}): {sample}", labels


def community_digest(root: Path, *, limit: int = 40) -> list[dict]:
    """Bounded brief for host-agent refinement (optional)."""
    by_comm = collect_community_paths(root)
    rows: list[dict] = []
    for cid in sorted(by_comm, key=lambda c: len(by_comm[c]), reverse=True)[:limit]:
        paths = by_comm[cid]
        rows.append(
            {
                "community": cid,
                "nodes_hint": len(paths),
                "sample_paths": sorted(set(paths))[:6],
                "heuristic_name": _heuristic_name(paths),
            }
        )
    return rows
