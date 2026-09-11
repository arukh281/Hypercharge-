"""Debounced graph refresh queue — fed by afterFileEdit hook."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from hypercharge.graph import graph_is_present, run_graphify_build
from hypercharge.paths import CURSOR_HYPERCHARGE

_QUEUE_FILE = "graph-refresh-queue.json"
_LAST_DRAIN = "last-graph-drain.json"
_DEBOUNCE_SEC = 25
_BATCH_THRESHOLD = 3


def _utc_now() -> str:
    """Internal _utc_now. Returns: datetime.now(timezone.utc).replace(microsecond=0).. (hypercharge-managed)"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def queue_path(root: Path) -> Path:
    """Queue path. Args: root. Returns: root.resolve() / CURSOR_HYPERCHARGE / _QUEUE_FILE. (hypercharge-managed)"""
    return root.resolve() / CURSOR_HYPERCHARGE / _QUEUE_FILE


def load_queue(root: Path) -> dict:
    """Load queue. Args: root. Returns: {'paths': [], 'enqueued_at': None}. (hypercharge-managed)"""
    path = queue_path(root)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"paths": [], "enqueued_at": None}


def enqueue_graph_refresh(root: Path, file_path: str) -> None:
    """Enqueue graph refresh. Args: root, file_path. (hypercharge-managed)"""
    data = load_queue(root)
    paths = list(data.get("paths") or [])
    rel = file_path.strip().lstrip("./")
    if rel and rel not in paths:
        paths.append(rel)
    data["paths"] = paths[-50:]
    data["enqueued_at"] = _utc_now()
    path = queue_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def clear_queue(root: Path) -> list[str]:
    """Clear queue. Args: root. Returns: paths. (hypercharge-managed)"""
    data = load_queue(root)
    paths = list(data.get("paths") or [])
    path = queue_path(root)
    if path.is_file():
        path.write_text(json.dumps({"paths": [], "enqueued_at": None}, indent=2) + "\n", encoding="utf-8")
    return paths


def pending_count(root: Path) -> int:
    """Pending count. Args: root. Returns: len(load_queue(root).get('paths') or []). (hypercharge-managed)"""
    return len(load_queue(root).get("paths") or [])


def _last_drain_path(root: Path) -> Path:
    """Internal _last_drain_path. Args: root. Returns: root.resolve() / CURSOR_HYPERCHARGE / _LAST_DRAIN. (hypercharge-managed)"""
    return root.resolve() / CURSOR_HYPERCHARGE / _LAST_DRAIN


def _last_drain_ts(root: Path) -> float:
    """Internal _last_drain_ts. Args: root. Returns: 0.0. (hypercharge-managed)"""
    p = _last_drain_path(root)
    if not p.is_file():
        return 0.0
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return float(data.get("ts", 0))
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return 0.0


def _mark_drained(root: Path) -> None:
    """Internal _mark_drained. Args: root. (hypercharge-managed)"""
    p = _last_drain_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"ts": time.time()}, indent=2) + "\n", encoding="utf-8")


def drain_if_ready(root: Path, *, debounce_sec: float = _DEBOUNCE_SEC) -> bool:
    """Drain graph refresh queue when batch threshold met or debounce elapsed."""
    root = root.resolve()
    pending = pending_count(root)
    if pending == 0:
        return False
    if pending < _BATCH_THRESHOLD and (time.time() - _last_drain_ts(root)) < debounce_sec:
        return False
    if not graph_is_present(root):
        clear_queue(root)
        return False

    paths = clear_queue(root)
    ok, _ = run_graphify_build(root, update=True, export_viz=False)
    if ok:
        _mark_drained(root)
        return True
    if paths:
        data = {"paths": paths, "enqueued_at": None}
        queue_path(root).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return False
