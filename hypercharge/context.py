"""Agent context stack — graphify grounding + shrink (auto-install, no bare failures)."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from hypercharge.compress_output import compress_text
from hypercharge.graph import (
    ensure_graphify,
    graph_is_present,
    graph_json_path,
    graphify_cmd,
    graphify_available,
    run_graphify_build,
    _graphify_env,
)
from hypercharge.grounding_gate import assess_query_output, extract_citations
from hypercharge.grounding_session import record_query_success
from hypercharge.inventory import load_repo_profile
from hypercharge.paths import resolve_hypercharge_source
from hypercharge.ui.console import HyperConsole

DEFAULT_QUERY_BUDGET = 1500
DEFAULT_SHRINK_CHARS = 12_000


def _graph_age_days(root: Path) -> int | None:
    """Internal _graph_age_days. Args: root. Returns: (datetime.now(timezone.utc) - mtime).days. (hypercharge-managed)"""
    p = graph_json_path(root)
    if not p.is_file():
        return None
    mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
    return (datetime.now(timezone.utc) - mtime).days


def _stale_threshold_days(root: Path) -> int:
    """Internal _stale_threshold_days. Args: root. Returns: int((profile.get('graph') or {}).get('stale_after_. (hypercharge-managed)"""
    profile = load_repo_profile(root) or {}
    return int((profile.get("graph") or {}).get("stale_after_days", 14))


def _community_map_preamble(root: Path, question: str = "", *, limit: int = 8) -> str:
    """Short module map from community labels — query-relevant when possible."""
    from hypercharge.community_labels import load_labels

    labels = load_labels(root)
    if not labels:
        return ""
    q_tokens = {t.lower() for t in question.replace("/", " ").split() if len(t) > 2}
    scored: list[tuple[int, int, str]] = []
    for cid, name in labels.items():
        score = sum(1 for t in q_tokens if t in name.lower())
        scored.append((score, cid, name))
    scored.sort(key=lambda x: (-x[0], x[1]))
    items = [(cid, name) for _, cid, name in scored[:limit]]
    lines = [f"  {cid}: {name}" for cid, name in items]
    return "## Module map (communities)\n" + "\n".join(lines) + "\n\n"


def _label_to_repo_path(label: str) -> str | None:
    """Parse `hypercharge · hook_handlers.py` → `hypercharge/hook_handlers.py`."""
    label = (label or "").strip()
    if "·" in label:
        left, _, right = label.partition("·")
        left = left.strip().replace(" ", "/")
        right = right.strip()
        if right:
            return f"{left}/{right}" if left else right
    if "/" in label and label.endswith(".py"):
        return label.lstrip("./")
    return None


def _collect_graph_paths(root: Path) -> list[str]:
    """Repo-relative paths from graph.json nodes and community labels."""
    root = root.resolve()
    seen: set[str] = set()
    out: list[str] = []

    from hypercharge.community_labels import collect_community_paths, load_labels

    for paths in collect_community_paths(root).values():
        for p in paths:
            norm = p.replace("\\", "/").lstrip("./")
            if norm and norm not in seen and (root / norm).is_file():
                seen.add(norm)
                out.append(norm)

    for name in load_labels(root).values():
        parsed = _label_to_repo_path(str(name))
        if parsed and parsed not in seen and (root / parsed).is_file():
            seen.add(parsed)
            out.append(parsed)

    return out


def _score_path_against_question(path: str, tokens: set[str]) -> int:
    """Internal _score_path_against_question. Args: path, tokens. Returns: score. (hypercharge-managed)"""
    path_lower = path.lower().replace("/", " ").replace("_", " ")
    stem = Path(path).stem.lower()
    score = sum(2 for t in tokens if t in path_lower)
    score += sum(3 for t in tokens if t in stem or stem in t)
    return score


def _fallback_keyword_digest(root: Path, question: str, *, limit: int = 5) -> str:
    """
    When graphify query returns no path:line citations, rank candidate files from
    graph node paths + community labels matched to the question tokens.
    Returns an honest, ungrounded suggestion block — no fake :N citations.
    """
    tokens = {t.lower() for t in question.replace("/", " ").replace("_", " ").split() if len(t) > 2}
    if not tokens:
        return ""

    candidates = _collect_graph_paths(root)
    if not candidates:
        return ""

    ranked = sorted(
        ((_score_path_against_question(p, tokens), p) for p in candidates),
        key=lambda x: (-x[0], x[1]),
    )
    hits = [(score, p) for score, p in ranked if score > 0][:limit]
    if not hits and ranked:
        hits = ranked[: min(limit, 3)]

    if not hits:
        return ""

    lines: list[str] = ["UNVERIFIED — no graph citations; candidate files to read:"]
    for _score, rel in hits:
        lines.append(f"- {rel}")
    return "\n".join(lines) + "\n"


def _ungrounded_candidates(root: Path, question: str, preamble: str) -> tuple[int, str] | None:
    """Return (1, text) listing honest candidate files when graphify yields no real citations."""
    candidates = _fallback_keyword_digest(root, question)
    if not candidates.strip():
        return None
    return 1, preamble + candidates


def ensure_context_ready(
    hc_root: Path | None = None,
    *,
    console: HyperConsole | None = None,
    air_gap: bool = False,
) -> bool:
    """Graphify available in hypercharge venv — install slim stack if needed."""
    hc = (hc_root or resolve_hypercharge_source()).resolve()
    if graphify_available(hc):
        return True
    c = console or HyperConsole(plain=True)
    return ensure_graphify(c, air_gap=air_gap, hc_root=hc)


def _run_graphify_query(
    root: Path,
    question: str,
    *,
    budget: int,
    hc_root: Path,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    """Internal _run_graphify_query. Args: root, question. Returns: subprocess.run([*graphify_cmd(hc_root), 'query', q. (hypercharge-managed)"""
    return subprocess.run(
        [*graphify_cmd(hc_root), "query", question, "--budget", str(budget)],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_graphify_env(root),
    )


def _maybe_refresh_stale_graph(
    root: Path,
    *,
    hc_root: Path,
    console: HyperConsole,
    air_gap: bool,
) -> None:
    """Internal _maybe_refresh_stale_graph. Args: root. (hypercharge-managed)"""
    age = _graph_age_days(root)
    threshold = _stale_threshold_days(root)
    if age is not None and age >= threshold:
        run_graphify_build(
            root,
            update=True,
            export_viz=False,
            hc_root=hc_root,
            console=console,
            air_gap=air_gap,
        )


def run_grounded_query(
    root: Path,
    question: str,
    *,
    budget: int = DEFAULT_QUERY_BUDGET,
    console: HyperConsole | None = None,
    air_gap: bool = False,
    build: bool = True,
) -> tuple[int, str]:
    """Graphify query. Returns (exit_code, text).

    build=True  (default; user-invoked query/knowledge/MCP) installs and builds
                or refreshes the graph as needed.
    build=False (hook/advisory path) NEVER installs, builds, or refreshes — if
                the tool or graph isn't ready it returns (1, "") so the hook stays
                silent and off the agent's critical path. Only an already-present
                graph is queried; a sparse result yields honest candidate files,
                never a synchronous rebuild.
    """
    root = root.resolve()
    hc_root = resolve_hypercharge_source(root)
    c = console or HyperConsole(plain=True)

    from hypercharge.graph import ensure_graphify_layout

    ensure_graphify_layout(root)

    if not build:
        if not graphify_available(hc_root) or not graph_is_present(root):
            return 1, ""
    else:
        if not ensure_context_ready(hc_root, console=c, air_gap=air_gap):
            return (
                1,
                "UNVERIFIED — graphify not installed. Run hypercharge setup in this repo, "
                "then read source files.",
            )
        if not graph_is_present(root):
            ok, msg = run_graphify_build(
                root,
                update=True,
                export_viz=False,
                hc_root=hc_root,
                console=c,
                air_gap=air_gap,
            )
            if not ok:
                return 1, f"UNVERIFIED — graph build failed ({msg}). Read source files."
        else:
            _maybe_refresh_stale_graph(root, hc_root=hc_root, console=c, air_gap=air_gap)

    preamble = _community_map_preamble(root, question)

    try:
        proc = _run_graphify_query(root, question, budget=budget, hc_root=hc_root)
        out = (proc.stdout or "").strip()
        assessment = assess_query_output(
            out, proc_returncode=proc.returncode, stderr=proc.stderr or "", root=root
        )
        if assessment.is_grounded:
            cites = extract_citations(out)
            record_query_success(root, [p for p, _ in cites])
            return 0, preamble + assessment.body

        fb = _ungrounded_candidates(root, question, preamble)
        if fb is not None:
            return fb

        if build:
            ok, _ = run_graphify_build(
                root,
                update=True,
                export_viz=False,
                hc_root=hc_root,
                console=c,
                air_gap=air_gap,
            )
            if ok:
                proc = _run_graphify_query(root, question, budget=budget, hc_root=hc_root)
                out = (proc.stdout or "").strip()
                assessment = assess_query_output(
                    out, proc_returncode=proc.returncode, stderr=proc.stderr or "", root=root
                )
                if assessment.is_grounded:
                    cites = extract_citations(out)
                    record_query_success(root, [p for p, _ in cites])
                    return 0, preamble + assessment.body

            fb = _ungrounded_candidates(root, question, preamble)
            if fb is not None:
                return fb

        return assessment.exit_code, preamble + assessment.body
    except FileNotFoundError:
        return (1, "") if not build else (1, "UNVERIFIED — graphify binary missing. Run hypercharge setup.")
    except subprocess.TimeoutExpired:
        return (1, "") if not build else (1, "UNVERIFIED — query timed out. Read source files.")


def shrink_for_context(
    text: str,
    *,
    max_chars: int = DEFAULT_SHRINK_CHARS,
    content_hint: str = "",
    air_gap: bool | None = None,
) -> tuple[str, str]:
    """Shrink fat tool output before reasoning — never raises."""
    try:
        return compress_text(text, max_chars=max_chars, content_hint=content_hint, air_gap=air_gap)
    except Exception:
        if len(text) <= max_chars:
            return text, "unchanged"
        return text[:max_chars] + "\n… [truncated] …\n", "fallback"
