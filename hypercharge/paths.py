"""Path helpers for Hypercharge."""

from __future__ import annotations

import os
import re
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
DIST_ROOT = PACKAGE_ROOT.parent
SKILL_SRC = PACKAGE_ROOT / "skill" / "hypercharge"
REPO_GUARDRAIL_SKILL_SRC = PACKAGE_ROOT / "skill" / "repo-guardrail"
VENDOR_ROOT = PACKAGE_ROOT / "vendor"
VENDOR_WHEELS = VENDOR_ROOT / "wheels"
VENDOR_MANIFEST = VENDOR_ROOT / "MANIFEST.json"

CURSOR_SESSION = Path(".cursor/session")
CURSOR_HYPERCHARGE = Path(".cursor/hypercharge")
CURSOR_GRAPHIFY_OUT = Path(".cursor/graphify-out")
CURSOR_RULES = Path(".cursor/rules")
CURSOR_SKILLS = Path(".cursor/skills/repo-guardrail")


def atomic_write_json(path: Path, data: object) -> None:
    """Write ``data`` as JSON to ``path`` atomically.

    Serialises to a temp file in the same directory, then ``os.replace`` (atomic on
    POSIX and Windows) so a concurrent reader — e.g. another hook process in the same
    session — never observes a half-written file. Raises OSError on failure; the temp
    file is cleaned up first.
    """
    import json
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".hc-tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, indent=2) + "\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def repo_root(start: Path | None = None) -> Path:
    """Repo root. Args: start. Returns: (start or Path.cwd()).resolve(). (hypercharge-managed)"""
    return (start or Path.cwd()).resolve()


def find_git_root(start: Path | None = None) -> Path | None:
    """Return git repo root or None."""
    import subprocess

    cwd = (start or Path.cwd()).resolve()
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        root = Path(out.stdout.strip())
        return root if root.is_dir() else None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def resolve_hypercharge_source(start: Path | None = None) -> Path:
    """Locate hypercharge package root (editable install or HYPERCHARGE_ROOT)."""
    import os

    env = os.environ.get("HYPERCHARGE_ROOT")
    if env:
        p = Path(env).expanduser().resolve()
        if (p / "pyproject.toml").is_file():
            return p

    if (DIST_ROOT / "pyproject.toml").is_file():
        return DIST_ROOT

    cwd = (start or Path.cwd()).resolve()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / "hypercharge"
        if (candidate / "pyproject.toml").is_file():
            return candidate
        if (parent / "pyproject.toml").is_file():
            try:
                text = (parent / "pyproject.toml").read_text(encoding="utf-8")
                if 'name = "hypercharge"' in text:
                    return parent
            except OSError:
                pass
    return DIST_ROOT


def ensure_hypercharge_venv(hc_root: Path) -> Path:
    """Create .venv if needed; return path to venv python."""
    import subprocess
    import sys

    hc_root = hc_root.resolve()
    venv = hc_root / ".venv"
    py = venv / "bin" / "python"
    if not py.is_file():
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    return py


def pip_install_editable(hc_root: Path, venv_python: Path) -> None:
    """Pip install editable. Args: hc_root, venv_python. (hypercharge-managed)"""
    import subprocess

    subprocess.run(
        [str(venv_python), "-m", "pip", "install", "-e", str(hc_root), "-q"],
        check=True,
    )


def hypercharge_venv_python(hc_root: Path) -> Path:
    """Hypercharge venv python. Args: hc_root. Returns: hc_root.resolve() / '.venv' / 'bin' / 'python'. (hypercharge-managed)"""
    return hc_root.resolve() / ".venv" / "bin" / "python"


def venv_bin(hc_root: Path, name: str) -> Path:
    """Venv bin. Args: hc_root, name. Returns: hc_root.resolve() / '.venv' / 'bin' / name. (hypercharge-managed)"""
    return hc_root.resolve() / ".venv" / "bin" / name


def user_config_dir() -> Path:
    """User config dir. Returns: Path.home() / '.config' / 'hypercharge'. (hypercharge-managed)"""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "hypercharge"
    return Path.home() / ".config" / "hypercharge"


def load_user_config() -> dict:
    """Read ~/.config/hypercharge/config.yaml if present."""
    import yaml

    path = user_config_dir() / "config.yaml"
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, yaml.YAMLError):
        return {}


def user_air_gap() -> bool:
    """User air gap. Returns: bool(load_user_config().get('air_gap')). (hypercharge-managed)"""
    return bool(load_user_config().get("air_gap"))


def cursor_skills_dir() -> Path:
    """Cursor skills dir. Returns: Path.home() / '.cursor' / 'skills' / 'hypercharge'. (hypercharge-managed)"""
    return Path.home() / ".cursor" / "skills" / "hypercharge"


def claude_skills_dir() -> Path:
    """Claude skills dir. Returns: Path.home() / '.claude' / 'skills' / 'hypercharge'. (hypercharge-managed)"""
    return Path.home() / ".claude" / "skills" / "hypercharge"


def global_skill_scan_bases() -> list[Path]:
    """User-global skill roots — Cursor and Claude Code (deduped by name when scanning)."""
    return [
        Path.home() / ".cursor" / "skills",
        Path.home() / ".cursor" / "skills-cursor",
        Path.home() / ".claude" / "skills",
    ]


def agent_skill_install_dirs() -> list[tuple[str, Path]]:
    """Agent skill install dirs. Returns: [('Cursor', cursor_skills_dir()), ('Claude Code', . (hypercharge-managed)"""
    return [
        ("Cursor", cursor_skills_dir()),
        ("Claude Code", claude_skills_dir()),
    ]


def sanitise_branch(branch: str) -> str:
    """Sanitise branch. Args: branch. Returns: re.sub('[^\\w\\-]+', '_', branch.replace('/', '_'). (hypercharge-managed)"""
    return re.sub(r"[^\w\-]+", "_", branch.replace("/", "_"))[:120]


def git_last_commit_ts(cwd: Path | None = None) -> int | None:
    """Return the unix timestamp of the last git commit, or None if not a repo."""
    import subprocess

    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%ct"],
            cwd=cwd or Path.cwd(),
            capture_output=True,
            text=True,
            timeout=5,
        )
        raw = out.stdout.strip()
        if out.returncode == 0 and raw:
            return int(raw)
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError, OSError):
        pass
    return None


def git_branch(cwd: Path | None = None) -> str:
    """Git branch. Args: cwd. Returns: out.stdout.strip() or 'main'. (hypercharge-managed)"""
    import subprocess

    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd or Path.cwd(),
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip() or "main"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "main"
