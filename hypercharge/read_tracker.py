"""Read-before-write — file must be Read (snapshot) before Write/Edit."""

from __future__ import annotations

import hashlib
from pathlib import Path

from hypercharge.grounding_session import dev_repo_mode, is_dev_path, load_grounding, normalize_repo_path, save_grounding


def _file_hash(abs_path: Path) -> str:
    """Internal _file_hash. Args: abs_path. Returns: hashlib.sha256(data).hexdigest()[:16]. (hypercharge-managed)"""
    try:
        data = abs_path.read_bytes()
    except OSError:
        return ""
    return hashlib.sha256(data).hexdigest()[:16]


def record_read_snapshot(root: Path, path: str) -> None:
    """Record content hash when a Read is approved (pre-tool)."""
    norm = normalize_repo_path(root, path)
    if not norm:
        return
    abs_path = root.resolve() / norm
    if not abs_path.is_file():
        return
    h = _file_hash(abs_path)
    if not h:
        return
    data = load_grounding(root)
    snaps = data.get("read_snapshots") or {}
    if not isinstance(snaps, dict):
        snaps = {}
    snaps[norm] = {"hash": h}
    data["read_snapshots"] = snaps
    save_grounding(root, data)


def read_before_write_ok(root: Path, path: str) -> tuple[bool, str]:
    """Return (ok, reason) for editing path."""
    norm = normalize_repo_path(root, path)
    if not norm:
        return True, ""
    if dev_repo_mode(root) and is_dev_path(root, norm):
        return True, ""
    abs_path = root.resolve() / norm
    if not abs_path.is_file():
        return True, ""
    data = load_grounding(root)
    snaps = data.get("read_snapshots") or {}
    snap = snaps.get(norm) if isinstance(snaps, dict) else None
    if not snap or not snap.get("hash"):
        return False, f"Read `{norm}` before editing — Hypercharge read-before-write."
    current = _file_hash(abs_path)
    if current != snap.get("hash"):
        return False, f"`{norm}` changed since last read — read it again before editing."
    return True, ""
