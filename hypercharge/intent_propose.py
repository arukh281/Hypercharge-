"""Minimal intent proposal from repo signals."""

from __future__ import annotations

from pathlib import Path

import yaml

from hypercharge.paths import git_branch


def propose_intent(root: Path) -> dict:
    branch = git_branch(root)
    role = "internal_lib"
    if (root / "experiments").is_dir() or branch.startswith(("ak/", "exp/", "experiment")):
        role = "personal_research"
    if (root / "docs").is_dir() and not (root / "src").is_dir():
        work_focus = "Documentation / research"
    else:
        work_focus = "Software engineering"

    return {
        "repo": root.name,
        "branch": branch,
        "role": role,
        "maturity": "exploratory" if role == "personal_research" else "stabilizing",
        "audience": "self" if role == "personal_research" else "team",
        "provenance": "unspecified",
        "work_focus": work_focus,
        "coupling": {"downstream_of": [], "upstream_for": []},
    }


def write_repo_intent(root: Path, intent: dict) -> Path:
    p = root / ".cursor/repo-intent.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.dump(intent, default_flow_style=False, allow_unicode=True), encoding="utf-8")
    return p
