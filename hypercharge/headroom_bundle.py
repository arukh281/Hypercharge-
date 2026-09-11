"""Lazy headroom install — slim wheel + minimal runtime deps."""

from __future__ import annotations

import subprocess
from pathlib import Path

from hypercharge.paths import VENDOR_ROOT, VENDOR_WHEELS, resolve_hypercharge_source

HEADROOM_SLIM_LOCK = VENDOR_ROOT / "locks" / "headroom-slim.txt"
HEADROOM_VERSION = "0.25.0"


def headroom_available(hc_root: Path | None = None) -> bool:
    hc = (hc_root or resolve_hypercharge_source()).resolve()
    vpy = hc / ".venv" / "bin" / "python"
    if not vpy.is_file():
        return False
    proc = subprocess.run(
        [str(vpy), "-c", "from headroom import compress"],
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def install_headroom_slim(
    hc_root: Path,
    venv_python: Path,
    *,
    air_gap: bool = False,
) -> bool:
    wheels = VENDOR_WHEELS
    find_links = ["--find-links", str(wheels)] if wheels.is_dir() else []
    offline = ["--no-index", *find_links] if air_gap else find_links

    matches = sorted(wheels.glob("headroom_ai-*.whl")) if wheels.is_dir() else []
    if matches:
        subprocess.run(
            [str(venv_python), "-m", "pip", "install", "-q", *offline, "--no-deps", str(matches[0])],
            check=False,
        )
    elif not air_gap:
        subprocess.run(
            [str(venv_python), "-m", "pip", "install", "-q", f"headroom-ai=={HEADROOM_VERSION}", "--no-deps"],
            check=False,
        )
    elif not matches:
        return False

    if HEADROOM_SLIM_LOCK.is_file():
        subprocess.run(
            [str(venv_python), "-m", "pip", "install", "-q", *offline, "-r", str(HEADROOM_SLIM_LOCK)],
            check=False,
        )
    elif not air_gap:
        subprocess.run(
            [
                str(venv_python),
                "-m",
                "pip",
                "install",
                "-q",
                "tiktoken>=0.5.0",
                "pydantic>=2.0",
                "click>=8.1",
                "rich>=13.0",
            ],
            check=False,
        )

    proc = subprocess.run(
        [str(venv_python), "-c", "from headroom import compress"],
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def ensure_headroom(hc_root: Path | None = None, *, air_gap: bool = False) -> bool:
    hc = (hc_root or resolve_hypercharge_source()).resolve()
    if headroom_available(hc):
        return True
    vpy = hc / ".venv" / "bin" / "python"
    if not vpy.is_file():
        return False
    return install_headroom_slim(hc, vpy, air_gap=air_gap)
