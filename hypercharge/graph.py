"""Graphify integration."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

from hypercharge.paths import CURSOR_GRAPHIFY_OUT, resolve_hypercharge_source, venv_bin

_LEGACY_GRAPHIFY_OUT = Path("graphify-out")

_LLM_KEY_VARS = (
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "MOONSHOT_API_KEY",
    "DEEPSEEK_API_KEY",
)


def has_llm_api_key() -> bool:
    """Has llm api key. Returns: any((os.environ.get(k) for k in _LLM_KEY_VARS)). (hypercharge-managed)"""
    return any(os.environ.get(k) for k in _LLM_KEY_VARS)


def graphify_available(hc_root: Path | None = None) -> bool:
    """Graphify available. Args: hc_root. Returns: importlib.util.find_spec('graphify') is not None. (hypercharge-managed)"""
    hc = (hc_root or resolve_hypercharge_source()).resolve()
    if venv_bin(hc, "graphify").is_file():
        return True
    if shutil.which("graphify"):
        return True
    return importlib.util.find_spec("graphify") is not None


def graphify_cmd(hc_root: Path | None = None) -> list[str]:
    """Argv prefix to invoke graphify — prefers hypercharge venv binary."""
    hc = (hc_root or resolve_hypercharge_source()).resolve()
    vg = venv_bin(hc, "graphify")
    if vg.is_file():
        return [str(vg)]
    if shutil.which("graphify"):
        return ["graphify"]
    vpy = venv_bin(hc, "python")
    if vpy.is_file() and importlib.util.find_spec("graphify"):
        return [str(vpy), "-m", "graphify"]
    return ["graphify"]


def ensure_graphify(console, air_gap: bool = False, hc_root: Path | None = None) -> bool:
    """Ensure graphify. Args: console, air_gap, hc_root. Returns: graphify_available(hc). (hypercharge-managed)"""
    hc = (hc_root or resolve_hypercharge_source()).resolve()
    if graphify_available(hc):
        return True
    vpy = hc / ".venv" / "bin" / "python"
    if not vpy.is_file():
        if air_gap:
            console.warn("Graphify not found — AST-only / no-graph mode.")
            return False
        console.warn("Hypercharge venv missing — create it with hypercharge onboard.")
        return False
    from hypercharge.bundle import install_graphify_stack

    console.warn("Installing slim graphify stack from vendor/wheels …")
    result = install_graphify_stack(hc, vpy, console=console, air_gap=air_gap)
    if not result.graphify:
        console.warn("Bundled graphify install failed — try scripts/vendor-sync.sh")
    return graphify_available(hc)


def _load_graph_config(root: Path) -> dict:
    """Internal _load_graph_config. Args: root. Returns: graph if isinstance(graph, dict) else {}. (hypercharge-managed)"""
    from hypercharge.inventory import load_repo_profile

    profile = load_repo_profile(root) or {}
    graph = profile.get("graph") or {}
    return graph if isinstance(graph, dict) else {}


def graphify_out_rel(root: Path) -> str:
    """Relative path for GRAPHIFY_OUT env (under repo root)."""
    graph = _load_graph_config(root)
    out = str(graph.get("output_dir", "")).strip().strip("/")
    if out.startswith("graphify-out") or (out and not out.startswith(".cursor/")):
        out = ""
    if out and (out.startswith(".cursor/") or out == ".cursor"):
        return out
    if path := graph.get("path"):
        parent = str(Path(path).parent).strip().strip("/")
        if parent.startswith("graphify-out") or not parent.startswith(".cursor/"):
            return str(CURSOR_GRAPHIFY_OUT)
        return parent
    return str(CURSOR_GRAPHIFY_OUT)


def graphify_out_dir(root: Path) -> Path:
    """Graphify out dir. Args: root. Returns: root.resolve() / graphify_out_rel(root). (hypercharge-managed)"""
    return root.resolve() / graphify_out_rel(root)


def graph_json_path(root: Path) -> Path:
    """Graph json path. Args: root. Returns: graphify_out_dir(root) / 'graph.json'. (hypercharge-managed)"""
    graph = _load_graph_config(root)
    if rel := graph.get("path"):
        return root.resolve() / rel
    return graphify_out_dir(root) / "graph.json"


def graph_report_path(root: Path) -> Path:
    """Graph report path. Args: root. Returns: graphify_out_dir(root) / 'GRAPH_REPORT.md'. (hypercharge-managed)"""
    graph = _load_graph_config(root)
    if rel := graph.get("report"):
        return root.resolve() / rel
    return graphify_out_dir(root) / "GRAPH_REPORT.md"


def graph_is_present(root: Path) -> bool:
    """Graph is present. Args: root. Returns: graph_json_path(root).is_file(). (hypercharge-managed)"""
    return graph_json_path(root).is_file()


def migrate_legacy_graphify_out(root: Path) -> bool:
    """Move repo-root graphify-out/ into .cursor/graphify-out/ when needed."""
    root = root.resolve()
    legacy = root / _LEGACY_GRAPHIFY_OUT
    target = root / CURSOR_GRAPHIFY_OUT
    if not legacy.is_dir():
        return False
    if legacy.resolve() == target.resolve():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        shutil.move(str(legacy), str(target))
        return True
    for item in legacy.rglob("*"):
        if item.is_file():
            rel = item.relative_to(legacy)
            dest = target / rel
            if not dest.is_file():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest)
    shutil.rmtree(legacy)
    return True


def ensure_graphify_layout(root: Path) -> None:
    """Ensure graph lives under .cursor/graphify-out and profile paths match."""
    from hypercharge.inventory import load_repo_profile, save_repo_profile

    root = root.resolve()
    migrate_legacy_graphify_out(root)

    profile = load_repo_profile(root) or {}
    graph = profile.setdefault("graph", {})
    if not isinstance(graph, dict):
        graph = {}
        profile["graph"] = graph

    current_out = str(graph.get("output_dir", "")).strip().strip("/")
    # Only accept paths that live under .cursor/ — never trust a bare or absolute path.
    _safe = current_out.startswith(".cursor/") or current_out == ".cursor"
    if current_out and _safe:
        rel = current_out
    else:
        rel = str(CURSOR_GRAPHIFY_OUT)  # ".cursor/graphify-out"

    (root / rel).mkdir(parents=True, exist_ok=True)

    defaults = {
        "output_dir": rel,
        "path": f"{rel}/graph.json",
        "html": f"{rel}/graph.html",
        "tree_html": f"{rel}/GRAPH_TREE.html",
        "report": f"{rel}/GRAPH_REPORT.md",
    }
    changed = False
    for key, value in defaults.items():
        current = str(graph.get(key, "")).strip()
        # Rewrite if empty, if it's a bare root-level path (legacy "graphify-out/…"),
        # or if it escapes .cursor/ entirely.
        needs_rewrite = (
            not current
            or current.startswith("graphify-out")
            or not current.startswith(".cursor/")
        )
        if needs_rewrite:
            graph[key] = value
            changed = True
    if changed:
        save_repo_profile(root, profile)


def _graphify_env(root: Path) -> dict[str, str]:
    """Internal _graphify_env. Args: root. Returns: env. (hypercharge-managed)"""
    ensure_graphify_layout(root)
    env = os.environ.copy()
    env["GRAPHIFY_OUT"] = graphify_out_rel(root)
    return env


def validate_setup_root(root: Path) -> list[str]:
    """Return warning messages if root looks like the wrong directory."""
    warnings: list[str] = []
    root = root.resolve()
    parts = {p.lower() for p in root.parts}
    home = Path.home().resolve()

    if "skills" in parts and root.name.lower() == "skills":
        warnings.append(
            "You are inside a global skills folder — run setup from your project repo, e.g.\n"
            '  cd "/path/to/your-repo" && hypercharge setup'
        )
    if root.is_relative_to(home / ".cursor" / "skills") or root.is_relative_to(
        home / ".claude" / "skills"
    ):
        warnings.append("Setup target is under global skills — use your git project root instead.")

    if not (root / ".git").exists():
        if not (root / "pyproject.toml").exists():
            warnings.append(
                "No .git here — if this is not your repo root, pass --path /path/to/repo"
            )
    return warnings


def graph_html_path(root: Path) -> Path:
    """Graph html path. Args: root. Returns: graphify_out_dir(root) / 'graph.html'. (hypercharge-managed)"""
    graph = _load_graph_config(root)
    if rel := graph.get("html"):
        return root.resolve() / rel
    return graphify_out_dir(root) / "graph.html"


def graph_tree_path(root: Path) -> Path:
    """Graph tree path. Args: root. Returns: graphify_out_dir(root) / 'GRAPH_TREE.html'. (hypercharge-managed)"""
    graph = _load_graph_config(root)
    if rel := graph.get("tree_html"):
        return root.resolve() / rel
    return graphify_out_dir(root) / "GRAPH_TREE.html"


def graph_node_count(root: Path) -> int | None:
    """Graph node count. Args: root. Returns: None. (hypercharge-managed)"""
    p = graph_json_path(root)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return len(data.get("nodes", []))
    except (json.JSONDecodeError, OSError):
        return None


def _run_graphify_subcmd(
    root: Path,
    args: list[str],
    *,
    timeout: int = 900,
    hc_root: Path | None = None,
    console=None,
    air_gap: bool = False,
) -> tuple[bool, str]:
    """Internal _run_graphify_subcmd. Args: root, args. Returns: (True, out or 'ok'). (hypercharge-managed)"""
    hc = (hc_root or resolve_hypercharge_source(root)).resolve()
    if not graphify_available(hc):
        from hypercharge.ui.console import HyperConsole

        c = console or HyperConsole(plain=True)
        if not ensure_graphify(c, air_gap=air_gap, hc_root=hc):
            return False, "graphify not installed"
    cmd = [*graphify_cmd(hc), *args]
    try:
        proc = subprocess.run(
            cmd,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_graphify_env(root),
        )
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if proc.returncode != 0:
            return False, err or out or f"graphify {' '.join(args)} failed"
        return True, out or "ok"
    except FileNotFoundError:
        return False, "graphify command not found"
    except subprocess.TimeoutExpired:
        return False, f"graphify {' '.join(args)} timed out"


def run_graphify_exports(
    root: Path,
    *,
    html: bool = True,
    tree: bool = True,
    hc_root: Path | None = None,
) -> dict[str, tuple[bool, str]]:
    """Write browser-friendly graph artifacts after graph.json exists."""
    root = root.resolve()
    results: dict[str, tuple[bool, str]] = {}
    if html:
        results["html"] = _run_graphify_subcmd(root, ["export", "html"], hc_root=hc_root)
    if tree:
        results["tree"] = _run_graphify_subcmd(root, ["tree"], hc_root=hc_root)
    return results


def run_graphify_label(root: Path, hc_root: Path | None = None) -> tuple[bool, str]:
    """Legacy graphify API label — prefer host-agent naming (no API key)."""
    from hypercharge.community_labels import name_communities_for_host_agent

    ok, msg, _ = name_communities_for_host_agent(root, hc_root=hc_root, force=True)
    return ok, msg


def graph_artifacts_summary(root: Path) -> list[str]:
    """Plain-language lines for setup footer / agent replies."""
    lines: list[str] = []
    nodes = graph_node_count(root)
    rel = graphify_out_rel(root)
    if graph_html_path(root).is_file():
        view = "community overview" if nodes and nodes > 5000 else "interactive map"
        lines.append(f"Code map (browser): {rel}/graph.html ({view})")
    if graph_tree_path(root).is_file():
        lines.append(f"Folder tree (browser): {rel}/GRAPH_TREE.html")
    if nodes:
        lines.append(f"Code map (data): {rel}/graph.json — {nodes} nodes")
    return lines


def run_graphify_build(
    root: Path,
    *,
    update: bool = True,
    semantic: bool = False,
    export_viz: bool = False,
    label_communities: bool = False,
    hc_root: Path | None = None,
    console=None,
    air_gap: bool = False,
) -> tuple[bool, str]:
    """Build or refresh graph. Always uses `graphify update` (code/AST, no API key).

    Semantic doc extraction is **not** run from CLI — use the graphify skill in
    chat (Cursor or Claude Code; host agent = LLM).
    """
    root = root.resolve()
    hc = (hc_root or resolve_hypercharge_source(root)).resolve()
    if not graphify_available(hc):
        from hypercharge.ui.console import HyperConsole

        c = console or HyperConsole(plain=True)
        if not ensure_graphify(c, air_gap=air_gap, hc_root=hc):
            return False, "graphify not installed — run hypercharge setup"
    _ = semantic  # reserved; CLI never calls external LLM APIs
    ensure_graphify_layout(root)
    cmd = [*graphify_cmd(hc), "update", str(root)]

    try:
        proc = subprocess.run(
            cmd,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=3600,
            env=_graphify_env(root),
        )
        if proc.returncode != 0:
            err = proc.stderr.strip() or proc.stdout.strip() or "graphify failed"
            return False, err

        notes: list[str] = ["ok (code/AST)"]
        if export_viz:
            exports = run_graphify_exports(root, hc_root=hc_root)
            for kind, (ok, msg) in exports.items():
                if ok:
                    notes.append(f"{kind} exported")
                else:
                    notes.append(f"{kind} export skipped: {msg}")
            from hypercharge.community_labels import name_communities_for_host_agent

            named_ok, named_msg, _ = name_communities_for_host_agent(root, hc_root=hc_root)
            if named_ok:
                notes.append(named_msg)
            else:
                notes.append(f"community names: {named_msg}")
        if label_communities:
            ok, msg = run_graphify_label(root, hc_root=hc_root)
            if ok:
                notes.append("communities named")
            else:
                notes.append(msg)
        return True, "; ".join(notes)
    except FileNotFoundError:
        return False, "graphify command not found"
    except subprocess.TimeoutExpired:
        return False, "graphify timed out"


def graph_hash(root: Path) -> str | None:
    """Graph hash. Args: root. Returns: None. (hypercharge-managed)"""
    p = graph_json_path(root)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        nodes = len(data.get("nodes", []))
        edges = len(data.get("edges") or data.get("links") or [])
        return f"{nodes}n_{edges}e"
    except (json.JSONDecodeError, OSError):
        return p.stat().st_mtime_ns.__str__()
