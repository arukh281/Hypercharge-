"""Per-session grounding tracker — which paths were queried or approved."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from hypercharge.paths import CURSOR_HYPERCHARGE
from hypercharge.session import get_open_chat_entry, peek_current_chat_id

_GROUNDING_FILE = "session-grounding.json"

# Writable/readable without prior query when dev_repo mode is on (Hypercharge self-build).
_DEFAULT_DEV_PREFIXES = (
    "hypercharge/",
    "tests/",
    "skill/",
    ".cursor/rules/",
    "pyproject.toml",
    "ARCHITECTURE.md",
    "README.md",
    "LICENCE",
)


def is_hypercharge_source_repo(root: Path) -> bool:
    """True when this git root is the Hypercharge package source (dogfooding)."""
    root = root.resolve()
    if not (root / "hypercharge" / "__init__.py").is_file():
        return False
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return False
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return False
    return 'name = "hypercharge"' in text or "name='hypercharge'" in text


def dev_repo_mode(root: Path) -> bool:
    """Relaxed grounding for building Hypercharge itself — safety denials still apply."""
    from hypercharge.inventory import load_repo_profile

    profile = load_repo_profile(root) or {}
    autonomy = profile.get("autonomy") or {}
    if isinstance(autonomy, dict):
        if autonomy.get("dev_repo") is True:
            return True
        if autonomy.get("dev_repo") is False:
            return False
    return is_hypercharge_source_repo(root)


def dev_path_prefixes(root: Path) -> tuple[str, ...]:
    """Dev path prefixes. Args: root. Returns: _DEFAULT_DEV_PREFIXES. (hypercharge-managed)"""
    from hypercharge.inventory import load_repo_profile

    profile = load_repo_profile(root) or {}
    autonomy = profile.get("autonomy") or {}
    if isinstance(autonomy, dict):
        raw = autonomy.get("dev_paths")
        if isinstance(raw, list) and raw:
            return tuple(str(p).rstrip("/") for p in raw)
    return _DEFAULT_DEV_PREFIXES


def is_dev_path(root: Path, target: str) -> bool:
    """True when path is in the dev allowlist (package, tests, project meta)."""
    target = normalize_repo_path(root, target)
    if not target:
        return False
    for prefix in dev_path_prefixes(root):
        p = prefix.rstrip("/")
        if p == target or target.startswith(p + "/"):
            return True
        if "/" not in p and target == p:
            return True
    return False


def _utc_now() -> str:
    """Internal _utc_now. Returns: datetime.now(timezone.utc).replace(microsecond=0).. (hypercharge-managed)"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def grounding_path(root: Path) -> Path:
    """Per-session grounding file when a session id is set, else the shared file."""
    from hypercharge.session_scope import session_slug

    base = root.resolve() / CURSOR_HYPERCHARGE
    slug = session_slug()
    if slug:
        return base / "sessions" / slug / _GROUNDING_FILE
    return base / _GROUNDING_FILE


def normalize_repo_path(root: Path, raw: str) -> str:
    """Canonical repo-relative POSIX path for grounding checks."""
    raw = (raw or "").strip().strip("'\"")
    if not raw:
        return ""
    root = root.resolve()
    norm = raw.replace("\\", "/").lstrip("./")

    candidates: list[Path] = [root / norm]
    if raw.startswith("/"):
        candidates.insert(0, Path(raw))
    elif not raw.startswith("./") and "/" in norm:
        candidates.append(Path("/" + norm))

    for candidate in candidates:
        try:
            rel = candidate.resolve().relative_to(root)
            return str(rel).replace("\\", "/")
        except (ValueError, OSError):
            continue

    parts = norm.split("/")
    root_parts = [p.lower() for p in root.parts]
    for i, part in enumerate(parts):
        if part.lower() in root_parts:
            idx = [p.lower() for p in parts].index(part.lower())
            tail = "/".join(parts[idx + 1 :])
            if tail:
                return tail
    return norm


def load_grounding(root: Path) -> dict:
    """Load grounding. Args: root. Returns: {'updated_at': None, 'queried_paths': [], 'approve. (hypercharge-managed)"""
    path = grounding_path(root)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"updated_at": None, "queried_paths": [], "approved_paths": [], "read_snapshots": {}}


def save_grounding(root: Path, data: dict) -> bool:
    """Persist session grounding atomically. Best-effort: returns False when the write
    is blocked (e.g. a read-only sandbox) rather than raising, since grounding is an
    advisory optimisation — a dropped write only costs a re-query, never correctness."""
    from hypercharge.paths import atomic_write_json

    try:
        data["updated_at"] = _utc_now()
        atomic_write_json(grounding_path(root), data)
        return True
    except OSError:
        return False


def _normalize_path_set(root: Path, paths: list[str]) -> list[str]:
    """Internal _normalize_path_set. Args: root, paths. Returns: out. (hypercharge-managed)"""
    out: list[str] = []
    seen: set[str] = set()
    for p in paths:
        norm = normalize_repo_path(root, p)
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


def record_query_success(root: Path, paths: list[str]) -> None:
    """Record paths from a successful grounded query."""
    data = load_grounding(root)
    seen = set(data.get("queried_paths") or [])
    for p in _normalize_path_set(root, paths):
        seen.add(p)
    data["queried_paths"] = sorted(seen)
    save_grounding(root, data)


def record_approved_path(root: Path, path: str) -> None:
    """Record approved path. Args: root, path. (hypercharge-managed)"""
    data = load_grounding(root)
    approved = set(data.get("approved_paths") or [])
    norm = normalize_repo_path(root, path)
    if norm:
        approved.add(norm)
    data["approved_paths"] = sorted(approved)
    save_grounding(root, data)


def _files_touched(root: Path) -> set[str]:
    """Internal _files_touched. Args: root. Returns: out. (hypercharge-managed)"""
    chat_id = peek_current_chat_id(root)
    if not chat_id:
        return set()
    entry = get_open_chat_entry(root, chat_id)
    out: set[str] = set()
    for f in entry.get("files_touched") or []:
        norm = normalize_repo_path(root, str(f))
        if norm:
            out.add(norm)
    return out


def is_path_grounded(root: Path, target: str) -> bool:
    """True if path was queried, approved, already touched, or dev-repo allowlisted."""
    target = normalize_repo_path(root, target)
    if not target:
        return True
    if dev_repo_mode(root) and is_dev_path(root, target):
        return True
    data = load_grounding(root)
    queried = {normalize_repo_path(root, p) for p in (data.get("queried_paths") or [])}
    approved = {normalize_repo_path(root, p) for p in (data.get("approved_paths") or [])}
    touched = _files_touched(root)
    return target in queried or target in approved or target in touched


def grounding_policy(root: Path) -> str:
    """warn | block | off — from repo-profile autonomy."""
    from hypercharge.inventory import load_repo_profile

    profile = load_repo_profile(root) or {}
    autonomy = profile.get("autonomy") or {}
    if isinstance(autonomy, dict):
        mode = autonomy.get("grounding_gate", "")
        if mode in ("off", "warn", "block"):
            if dev_repo_mode(root) and mode == "block":
                return "warn"
            return mode

    if dev_repo_mode(root):
        return "warn"

    return "off"
