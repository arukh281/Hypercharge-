"""Repo-local runtime paths — written at setup/onboard for hook scripts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from hypercharge.paths import CURSOR_HYPERCHARGE, hypercharge_venv_python, resolve_hypercharge_source

_RUNTIME_FILE = "runtime.json"


def runtime_json_path(root: Path) -> Path:
    return root.resolve() / CURSOR_HYPERCHARGE / _RUNTIME_FILE


def write_runtime_manifest(root: Path, *, hc_root: Path | None = None) -> Path:
    """Record hypercharge python path for Cursor hook shell scripts."""
    root = root.resolve()
    hc = (hc_root or resolve_hypercharge_source(root)).resolve()
    vpy = hypercharge_venv_python(hc)
    if not vpy.is_file():
        vpy = Path(sys.executable)

    data = {
        "hypercharge_python": str(vpy),
        "hypercharge_root": str(hc),
        "schema_version": 1,
    }
    out = runtime_json_path(root)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return out


def load_runtime_manifest(root: Path) -> dict:
    path = runtime_json_path(root)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def resolve_hook_python(root: Path) -> Path | None:
    """Python executable for hooks — runtime.json first."""
    data = load_runtime_manifest(root)
    raw = data.get("hypercharge_python")
    if raw:
        p = Path(str(raw))
        if p.is_file():
            return p
    hc = data.get("hypercharge_root")
    if hc:
        vpy = hypercharge_venv_python(Path(hc))
        if vpy.is_file():
            return vpy
    return None
