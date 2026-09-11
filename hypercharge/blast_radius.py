"""Blast radius analysis — how many things depend on a given file."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

_DEPENDENCY_RELATIONS = frozenset({"imports", "calls", "uses", "imports_from"})


@dataclass(frozen=True)
class BlastRadius:
    file: str
    dependent_files: list[str]
    test_files: list[str]
    callsite_count: int
    risk_level: str  # "low" | "medium" | "high" | "unknown"
    summary: str


def _is_test_file(path: str) -> bool:
    """Internal _is_test_file. Args: path. Returns: 'test' in p.split('/')[-1] or p.startswith('tests/. (hypercharge-managed)"""
    p = path.replace("\\", "/")
    return "test" in p.split("/")[-1] or p.startswith("tests/") or "/tests/" in p


def _normalize(path: str, root: Path) -> str:
    """Return a normalised relative-path string for comparison."""
    try:
        p = Path(path)
        if p.is_absolute():
            try:
                return str(p.relative_to(root.resolve()))
            except ValueError:
                return path
        return str(p)
    except Exception:
        return path


def _risk(count: int) -> str:
    """Internal _risk. Args: count. Returns: 'high'. (hypercharge-managed)"""
    if count <= 2:
        return "low"
    if count <= 8:
        return "medium"
    return "high"


def analyse(root: Path, file_path: str, *, max_deps: int = 20) -> BlastRadius:
    """
    Load graph.json and find all files that depend on file_path.
    Returns BlastRadius with risk assessment.
    """
    from hypercharge.graph import graph_json_path

    graph_path = graph_json_path(root)
    if not graph_path.is_file():
        return BlastRadius(
            file=file_path,
            dependent_files=[],
            test_files=[],
            callsite_count=0,
            risk_level="unknown",
            summary=f"{file_path}: graph not found — blast radius unknown",
        )

    try:
        data = json.loads(graph_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return BlastRadius(
            file=file_path,
            dependent_files=[],
            test_files=[],
            callsite_count=0,
            risk_level="unknown",
            summary=f"{file_path}: could not parse graph — blast radius unknown",
        )

    nodes: list[dict] = data.get("nodes") or []
    links: list[dict] = data.get("links") or []

    # Build node_id -> source_file map
    id_to_source: dict[str, str] = {}
    for node in nodes:
        nid = node.get("id")
        src = node.get("source_file") or ""
        if nid and src:
            id_to_source[nid] = src

    norm_target = _normalize(file_path, root)

    # Find all dependency edges whose target resolves to file_path
    dependent_set: set[str] = set()
    for link in links:
        if link.get("relation") not in _DEPENDENCY_RELATIONS:
            continue
        target_id = link.get("target") or ""
        target_src = id_to_source.get(target_id, link.get("target_file") or "")
        if not target_src:
            continue
        norm_tgt = _normalize(target_src, root)
        if norm_tgt != norm_target:
            continue
        source_id = link.get("source") or ""
        source_src = id_to_source.get(source_id, link.get("source_file") or "")
        if not source_src:
            continue
        norm_src = _normalize(source_src, root)
        if norm_src != norm_target:  # skip self-references
            dependent_set.add(norm_src)

    all_deps = sorted(dependent_set)[:max_deps]
    test_files = [f for f in all_deps if _is_test_file(f)]
    dependent_files = [f for f in all_deps if not _is_test_file(f)]
    callsite_count = len(all_deps)
    risk = _risk(callsite_count)

    if callsite_count == 0:
        summary = f"{file_path}: no dependents found (standalone)"
    else:
        summary = f"{file_path}: {callsite_count} dependent(s) — {risk} blast radius"

    return BlastRadius(
        file=file_path,
        dependent_files=dependent_files,
        test_files=test_files,
        callsite_count=callsite_count,
        risk_level=risk,
        summary=summary,
    )


def format_for_injection(br: BlastRadius) -> str:
    """Return a compact context block for agent injection."""
    risk_label = br.risk_level.upper()
    lines: list[str] = [f"## Blast radius: {br.file}"]

    if br.risk_level == "unknown":
        lines.append("Risk: UNKNOWN (graph unavailable)")
        return "\n".join(lines)

    if br.callsite_count == 0:
        lines.append("Risk: LOW (no dependents — standalone file)")
        return "\n".join(lines)

    lines.append(f"Risk: {risk_label} ({br.callsite_count} dependent(s))")

    all_deps = br.dependent_files + br.test_files
    if all_deps:
        dep_str = ", ".join(all_deps[:8])
        if len(all_deps) > 8:
            dep_str += f", … (+{len(all_deps) - 8} more)"
        lines.append(f"Depends on this: {dep_str}")

    if br.test_files:
        test_str = ", ".join(br.test_files[:5])
        lines.append(f"Test coverage: {test_str}")

    return "\n".join(lines)
