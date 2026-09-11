"""Deploy Hypercharge-managed Claude Code hooks — merge with user .claude/settings.json."""

from __future__ import annotations

import json
import shutil
import stat
from pathlib import Path
from typing import Any

from hypercharge.paths import PACKAGE_ROOT

TEMPLATES = PACKAGE_ROOT / "templates"
CLAUDE_HOOKS_TEMPLATE = TEMPLATES / "claude-hooks-template.json"
CLAUDE_HOOKS_SCRIPTS_DIR = TEMPLATES / "claude-hooks"
CURSOR_PYTHON_SH = TEMPLATES / "hooks" / "_hypercharge-python.sh"

MANAGED_CLAUDE_HOOK_PREFIX = "hypercharge-"


def _hook_commands(entry: dict[str, Any]) -> list[str]:
    """Internal _hook_commands. Args: entry. Returns: cmds. (hypercharge-managed)"""
    cmds: list[str] = []
    nested = entry.get("hooks") or []
    if isinstance(nested, list):
        for item in nested:
            if isinstance(item, dict):
                cmd = str(item.get("command") or "").strip()
                if cmd:
                    cmds.append(cmd)
    flat = str(entry.get("command") or "").strip()
    if flat:
        cmds.append(flat)
    return cmds


def is_managed_claude_hook_entry(entry: dict[str, Any]) -> bool:
    """Is managed claude hook entry. Args: entry. Returns: False. (hypercharge-managed)"""
    for cmd in _hook_commands(entry):
        if MANAGED_CLAUDE_HOOK_PREFIX in cmd and ".claude/hooks/" in cmd:
            return True
    return False


def merge_claude_settings(existing: dict[str, Any], managed_fragment: dict[str, Any]) -> dict[str, Any]:
    """Keep user settings; replace hypercharge-managed hook entries per event."""
    out = dict(existing)
    existing_hooks = (existing.get("hooks") or {}) if isinstance(existing.get("hooks"), dict) else {}
    managed_hooks = (managed_fragment.get("hooks") or {}) if isinstance(managed_fragment.get("hooks"), dict) else {}

    merged_hooks: dict[str, list] = {}
    all_events = set(existing_hooks) | set(managed_hooks)
    for event in sorted(all_events):
        user_entries = [
            e for e in (existing_hooks.get(event) or []) if not is_managed_claude_hook_entry(e)
        ]
        managed_entries = list(managed_hooks.get(event) or [])
        combined = user_entries + managed_entries
        if combined:
            merged_hooks[event] = combined
    if merged_hooks:
        out["hooks"] = merged_hooks
    elif "hooks" in out and not merged_hooks:
        out.pop("hooks", None)
    return out


def deploy_claude_hooks(root: Path) -> list[str]:
    """Sync Claude hook scripts and merge .claude/settings.json. Returns paths touched."""
    touched: list[str] = []
    if not CLAUDE_HOOKS_TEMPLATE.is_file():
        return touched

    hooks_dir = root / ".claude/hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    if CURSOR_PYTHON_SH.is_file():
        dest_py = hooks_dir / "_hypercharge-python.sh"
        shutil.copy2(CURSOR_PYTHON_SH, dest_py)
        dest_py.chmod(dest_py.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        touched.append(str(dest_py.relative_to(root)))

    if CLAUDE_HOOKS_SCRIPTS_DIR.is_dir():
        for script in sorted(CLAUDE_HOOKS_SCRIPTS_DIR.glob("hypercharge-*.sh")):
            dest = hooks_dir / script.name
            shutil.copy2(script, dest)
            dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            touched.append(str(dest.relative_to(root)))

    dest_settings = root / ".claude/settings.json"
    managed_fragment = json.loads(CLAUDE_HOOKS_TEMPLATE.read_text(encoding="utf-8"))
    if dest_settings.is_file():
        try:
            existing = json.loads(dest_settings.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    else:
        existing = {}

    merged = merge_claude_settings(existing if isinstance(existing, dict) else {}, managed_fragment)
    dest_settings.parent.mkdir(parents=True, exist_ok=True)
    dest_settings.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    touched.append(str(dest_settings.relative_to(root)))
    return touched


def claude_hooks_health(root: Path) -> list[str]:
    """Return warning strings if managed Claude hooks are missing."""
    issues: list[str] = []
    dest_settings = root / ".claude/settings.json"
    if not dest_settings.is_file():
        issues.append("claude_settings_missing")
        return issues
    try:
        data = json.loads(dest_settings.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        issues.append("claude_settings_invalid")
        return issues
    hooks = data.get("hooks") or {}
    for event in ("SessionStart", "UserPromptSubmit", "PostToolUse", "Stop"):
        entries = hooks.get(event) or []
        if not any(is_managed_claude_hook_entry(e) for e in entries):
            issues.append(f"claude_hooks_missing_{event}")
    for script in (
        "hypercharge-session-start.sh",
        "hypercharge-before-prompt.sh",
        "hypercharge-pre-tool.sh",
        "hypercharge-after-edit.sh",
        "hypercharge-after-response.sh",
        "hypercharge-after-shell.sh",
    ):
        if not (root / ".claude/hooks" / script).is_file():
            issues.append(f"claude_hook_script_missing_{script}")
    return issues
