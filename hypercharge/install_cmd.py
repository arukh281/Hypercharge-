"""Install command."""

from __future__ import annotations

from pathlib import Path

import yaml

from hypercharge import __version__
from hypercharge.bundle import load_manifest
from hypercharge.paths import (
    agent_skill_install_dirs,
    ensure_hypercharge_venv,
    pip_install_editable,
    resolve_hypercharge_source,
    user_config_dir,
)
from hypercharge.skill_packs import list_bundled_skills, sync_bundled_skills
from hypercharge.ui.console import HyperConsole
from hypercharge.ui import copy_en_gb as copy


def _write_config(org: str = "yourco", air_gap: bool = False) -> Path:
    cfg_dir = user_config_dir()
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = cfg_dir / "config.yaml"
    data: dict = {}
    if cfg_path.is_file():
        try:
            loaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            pass
    data.setdefault("org", org)
    data.setdefault("locale", "en-GB")
    data.setdefault("graph", {"extraction_mode": "host_agent"})
    if air_gap or "air_gap" not in data:
        data["air_gap"] = air_gap
    cfg_path.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")
    return cfg_path


def run_install(
    console: HyperConsole,
    *,
    org: str = "yourco",
    air_gap: bool = False,
    hc_root: Path | None = None,
    quiet: bool = False,
    target: str = "both",
) -> int:
    if not quiet:
        console.banner()
    steps = copy.INSTALL_STEPS
    total = len(steps)

    hc_root = (hc_root or resolve_hypercharge_source()).resolve()
    manifest = load_manifest()
    g_ver = (manifest.get("bundled") or {}).get("graphifyy", {}).get("version", "bundled")

    if not quiet:
        console.step_ok(f"CLI v{__version__}", 1, total)

    try:
        venv_python = ensure_hypercharge_venv(hc_root)
        pip_install_editable(hc_root, venv_python)
    except OSError as exc:
        if not quiet:
            console.step_fail("CLI venv", str(exc))
        return 1

    if not quiet:
        console.step_ok(
            f"Graphify v{g_ver} (slim — installs on first repo setup)",
            2,
            total,
        )

    bundled = list_bundled_skills(target=target)
    if not bundled:
        if not quiet:
            console.step_fail("Agent skills", "No bundled skills in package")
        return 1
    count, names = sync_bundled_skills(target=target)
    if not quiet:
        console.step_ok(
            f"Agent skills ({count} bundled — Cursor + Claude Code)",
            3,
            total,
        )

    _write_config(org=org, air_gap=air_gap)
    if quiet:
        return 0

    cfg = _write_config(org=org, air_gap=air_gap)

    skill_paths = " · ".join(str(p.parent) for _, p in agent_skill_install_dirs())
    rows = [
        ("CLI", "ok", __version__),
        ("Venv", "ok", f"lightweight — graphify on setup (~{g_ver} slim)"),
        ("Shrink", "ok", "built-in (hypercharge shrink)"),
        ("Agent skills", "ok", f"{count} in package → {skill_paths}"),
        ("Config", "ok", str(cfg)),
        ("Semantic extract", "ok", "Host agent in chat (Cursor or Claude — no export API key)"),
    ]
    console.health_table(rows)
    console.step_ok("Health check", 4, total)

    console.footer(
        "Ready",
        [
            "Lightweight machine install — CLI + skills only.",
            f"Graphify installs on first hypercharge setup (~slim stack, not full language pack).",
            f"Bundled skills: {', '.join(names)}.",
            "In a project chat, agent runs: hypercharge onboard",
            "",
            f"Venv: {hc_root / '.venv'}",
            f"Config: {cfg}",
        ],
    )
    return 0
