"""Code-map staleness detection."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from hypercharge.graph import graph_is_present, graph_json_path
from hypercharge.paths import git_last_commit_ts
from hypercharge.session import load_repo_profile_json


def graph_age_days(root: Path) -> int | None:
    """Days since graph.json was last written."""
    p = graph_json_path(root)
    if not p.is_file():
        return None
    mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
    return (datetime.now(timezone.utc) - mtime).days


def graph_stale_threshold_days(root: Path) -> int:
    """Profile threshold for age-based staleness (default 14d)."""
    profile = load_repo_profile_json(root)
    return int((profile.get("graph") or {}).get("stale_after_days", 14))


def graph_predates_last_commit(root: Path) -> bool:
    """True when graph.json is older than the most recent git commit."""
    p = graph_json_path(root)
    if not p.is_file():
        return False
    commit_ts = git_last_commit_ts(root)
    if commit_ts is None:
        return False
    return p.stat().st_mtime < commit_ts


def graph_stale_reason(root: Path) -> str | None:
    """Return why the code map is stale, or None when acceptable.

    Staleness is surfaced (in the context packet, and warned at wrapup); the refresh
    itself happens via the after-edit queue drained at wrapup, not from here.
    """
    if not graph_is_present(root):
        return "missing"
    if graph_predates_last_commit(root):
        return "predates_commit"
    age = graph_age_days(root)
    threshold = graph_stale_threshold_days(root)
    if age is not None and age >= threshold:
        return "age"
    return None
