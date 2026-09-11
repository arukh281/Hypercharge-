"""Deploy Hypercharge-managed Cursor hooks — merge with user hooks."""

from __future__ import annotations

import json
import os
import shutil
import stat
from pathlib import Path

from hypercharge.agent_target import deploys_claude, deploys_cursor, load_agent_target
from hypercharge.claude_hooks_deploy import claude_hooks_health
from hypercharge.paths import PACKAGE_ROOT
from hypercharge.runtime_paths import load_runtime_manifest

TEMPLATES = PACKAGE_ROOT / "templates"
HOOKS_TEMPLATE = TEMPLATES / "hooks.json"
HOOKS_SCRIPTS_DIR = TEMPLATES / "hooks"

MANAGED_HOOK_SCRIPT_PREFIX = "hypercharge-"


def is_managed_hook_entry(entry: dict) -> bool:
    cmd = str(entry.get("command") or "")
    return MANAGED_HOOK_SCRIPT_PREFIX in cmd and ".cursor/hooks/" in cmd


def merge_hooks_json(existing: dict, managed: dict) -> dict:
    """Keep user hooks; replace hypercharge-managed entries per event."""
    out: dict = {"version": managed.get("version", existing.get("version", 1)), "hooks": {}}
    existing_hooks = existing.get("hooks") or {}
    managed_hooks = managed.get("hooks") or {}

    all_events = set(existing_hooks) | set(managed_hooks)
    for event in sorted(all_events):
        user_entries = [
            e for e in (existing_hooks.get(event) or []) if not is_managed_hook_entry(e)
        ]
        managed_entries = list(managed_hooks.get(event) or [])
        combined = user_entries + managed_entries
        if combined:
            out["hooks"][event] = combined
    return out


def deploy_hooks(root: Path) -> list[str]:
    """Sync managed hook scripts and merge hooks.json. Returns paths touched."""
    touched: list[str] = []
    if not HOOKS_TEMPLATE.is_file():
        return touched

    hooks_dir = root / ".cursor/hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    if HOOKS_SCRIPTS_DIR.is_dir():
        for script in sorted(HOOKS_SCRIPTS_DIR.glob("*.sh")):
            if not script.name.startswith(("hypercharge-", "_hypercharge")):
                continue
            dest = hooks_dir / script.name
            shutil.copy2(script, dest)
            dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            touched.append(str(dest.relative_to(root)))

    dest_json = root / ".cursor/hooks.json"
    managed = json.loads(HOOKS_TEMPLATE.read_text(encoding="utf-8"))
    if dest_json.is_file():
        try:
            existing = json.loads(dest_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {"version": 1, "hooks": {}}
    else:
        existing = {"version": 1, "hooks": {}}

    merged = merge_hooks_json(existing, managed)
    dest_json.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    touched.append(str(dest_json.relative_to(root)))
    return touched


def cursor_hooks_health(root: Path) -> list[str]:
    """Return warning strings if managed Cursor hooks are missing."""
    issues: list[str] = []
    runtime = root / ".cursor/hypercharge/runtime.json"
    if not runtime.is_file():
        issues.append("runtime_json_missing")
    elif not load_runtime_manifest(root).get("hypercharge_python"):
        issues.append("runtime_python_missing")
    dest_json = root / ".cursor/hooks.json"
    if not dest_json.is_file():
        issues.append("hooks_missing")
    else:
        try:
            data = json.loads(dest_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            issues.append("hooks_json_invalid")
        else:
            hooks = data.get("hooks") or {}
            for event in (
                "sessionStart",
                "beforeSubmitPrompt",
                "preToolUse",
                "afterFileEdit",
                "afterAgentResponse",
            ):
                entries = hooks.get(event) or []
                if not any(is_managed_hook_entry(e) for e in entries):
                    issues.append(f"hooks_missing_{event}")
    for script in (
        "_hypercharge-python.sh",
        "hypercharge-session-start.sh",
        "hypercharge-before-prompt.sh",
        "hypercharge-pre-tool.sh",
        "hypercharge-after-edit.sh",
        "hypercharge-after-response.sh",
    ):
        if not (root / ".cursor/hooks" / script).is_file():
            issues.append(f"hook_script_missing_{script}")
    return issues


def hooks_health(root: Path) -> list[str]:
    """Return hook health issues for the repo's configured agent_target."""
    target = load_agent_target(root)
    issues: list[str] = []
    if deploys_cursor(target):
        issues.extend(cursor_hooks_health(root))
    if deploys_claude(target):
        issues.extend(claude_hooks_health(root))
    return issues
