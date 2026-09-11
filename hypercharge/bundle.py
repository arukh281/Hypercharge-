"""Install pinned graphify from vendor bundle with PyPI fallback."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from hypercharge.paths import VENDOR_MANIFEST, VENDOR_ROOT, VENDOR_WHEELS

SLIM_LOCK = VENDOR_ROOT / "locks" / "graphifyy-slim.txt"
GRAPHIFYY_VERSION = "0.8.39"


@dataclass
class BundleResult:
    graphify: bool = False
    graphify_version: str | None = None
    notes: list[str] = field(default_factory=list)


def load_manifest() -> dict:
    if not VENDOR_MANIFEST.is_file():
        return {}
    return json.loads(VENDOR_MANIFEST.read_text(encoding="utf-8"))


def _pip_install(venv_python: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    cmd = [str(venv_python), "-m", "pip", "install", "-q", *args]
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def _import_ok(venv_python: Path, snippet: str) -> bool:
    proc = subprocess.run(
        [str(venv_python), "-c", snippet],
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def _install_from_vendor(
    venv_python: Path,
    g_ver: str,
    g_wheel: Path,
    *,
    air_gap: bool,
) -> bool:
    if not VENDOR_WHEELS.is_dir() or not g_wheel.is_file():
        return False
    wheels_arg = str(VENDOR_WHEELS)
    find_links = ["--find-links", wheels_arg]
    offline = ["--no-index", *find_links] if air_gap else find_links
    try:
        _pip_install(venv_python, *offline, "--no-deps", str(g_wheel))
        lock = SLIM_LOCK if SLIM_LOCK.is_file() else VENDOR_ROOT / "locks" / "graphifyy-runtime.txt"
        if lock.is_file():
            _pip_install(venv_python, *offline, "-r", str(lock), check=False)
        return _import_ok(venv_python, "import graphify")
    except subprocess.CalledProcessError:
        return False


def _install_from_pypi(venv_python: Path, g_ver: str) -> bool:
    try:
        _pip_install(venv_python, f"graphifyy=={g_ver}")
        return _import_ok(venv_python, "import graphify")
    except subprocess.CalledProcessError:
        return False


def install_graphify_stack(
    hc_root: Path,
    venv_python: Path,
    *,
    console=None,
    air_gap: bool = False,
) -> BundleResult:
    """Install graphifyy + slim language stack into the hypercharge venv."""
    _ = hc_root
    result = BundleResult()
    manifest = load_manifest()
    bundled = manifest.get("bundled") or {}

    g_spec = bundled.get("graphifyy") or {}
    g_ver = g_spec.get("version", GRAPHIFYY_VERSION)
    g_wheel = VENDOR_WHEELS / g_spec.get("wheel", f"graphifyy-{g_ver}-py3-none-any.whl")
    result.graphify_version = g_ver

    if _install_from_vendor(venv_python, g_ver, g_wheel, air_gap=air_gap):
        result.graphify = True
        result.notes.append(f"graphifyy {g_ver} (vendor slim)")
    elif not air_gap and _install_from_pypi(venv_python, g_ver):
        result.graphify = True
        result.notes.append(f"graphifyy {g_ver} (PyPI)")
    else:
        if air_gap:
            result.notes.append("vendor wheels missing — run scripts/vendor-sync.sh")
        elif not g_wheel.is_file():
            result.notes.append(f"missing wheel {g_wheel.name}; PyPI install failed")
        else:
            result.notes.append("graphifyy install failed")

    if console and result.notes:
        for note in result.notes:
            if "failed" in note or "missing" in note:
                console.warn(note)
    return result


install_bundled_stack = install_graphify_stack
