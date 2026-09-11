"""Teardown command — reverse `hypercharge setup` on a repo."""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

from hypercharge.claude_hooks_deploy import is_managed_claude_hook_entry
from hypercharge.hooks_deploy import is_managed_hook_entry
from hypercharge.templates_deploy import MANAGED_RULES, RETIRED_MANAGED_RULES
from hypercharge.ui.console import HyperConsole

_LEGACY_GRAPHIFY_OUT = "graphify-out"

# Directories owned entirely by Hypercharge — removed wholesale.
_HC_DIRS = (
    ".cursor/hypercharge",
    ".cursor/session",
    ".cursor/graphify-out",
)

# Files owned entirely by Hypercharge — removed wholesale on full teardown only.
_HC_FILES = (
    ".cursor/hypercharge.lock",
    ".cursor/repo-profile.json",
    ".cursor/repo-intent.yaml",
)

# Managed + retired rule filenames — removed on cursor teardown.
_MANAGED_RULES = list(MANAGED_RULES) + list(RETIRED_MANAGED_RULES)

# Hook scripts deployed into .cursor/hooks/ and .claude/hooks/.
_HOOK_SCRIPT_PREFIXES = ("hypercharge-", "_hypercharge-")

# CLAUDE.md managed block markers.
_MANAGED_START = "<!-- hypercharge-managed:start -->"
_MANAGED_END = "<!-- hypercharge-managed:end -->"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _remove_path(p: Path, dry_run: bool, removed: list[str]) -> None:
    """Internal _remove_path. Args: p, dry_run, removed. (hypercharge-managed)"""
    rel = str(p)
    try:
        rel = str(p.relative_to(Path.cwd()))
    except ValueError:
        pass
    if p.is_dir():
        if dry_run:
            removed.append(f"(dir)  {rel}/")
        else:
            shutil.rmtree(p, ignore_errors=True)
            removed.append(f"(dir)  {rel}/")
    elif p.is_file():
        if dry_run:
            removed.append(f"(file) {rel}")
        else:
            p.unlink(missing_ok=True)
            removed.append(f"(file) {rel}")


def _strip_cursor_hooks(hooks_json: Path, dry_run: bool) -> bool:
    """Remove hypercharge entries from .cursor/hooks.json; return True if changed."""
    if not hooks_json.is_file():
        return False
    try:
        data = json.loads(hooks_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False

    hooks = data.get("hooks") or {}
    new_hooks: dict = {}
    changed = False
    for event, entries in hooks.items():
        cleaned = [e for e in entries if not is_managed_hook_entry(e)]
        if len(cleaned) != len(entries):
            changed = True
        if cleaned:
            new_hooks[event] = cleaned

    if not changed:
        return False
    if not dry_run:
        if new_hooks:
            data["hooks"] = new_hooks
            hooks_json.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        else:
            # No user hooks left — remove the file entirely.
            hooks_json.unlink(missing_ok=True)
    return True


def _strip_cursor_mcp(mcp_json: Path, dry_run: bool) -> bool:
    """Remove hypercharge entry from .cursor/mcp.json; delete file if empty."""
    if not mcp_json.is_file():
        return False
    try:
        data = json.loads(mcp_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    if not isinstance(data, dict):
        return False

    mcp = data.get("mcpServers") or {}
    if not isinstance(mcp, dict) or "hypercharge" not in mcp:
        return False

    mcp.pop("hypercharge")
    if mcp:
        data["mcpServers"] = mcp
    else:
        data.pop("mcpServers", None)

    if not dry_run:
        if data:
            mcp_json.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        else:
            mcp_json.unlink(missing_ok=True)
    return True


def _strip_claude_settings(settings: Path, dry_run: bool) -> bool:
    """Remove hypercharge managed hook entries from .claude/settings.json."""
    if not settings.is_file():
        return False
    try:
        data = json.loads(settings.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    if not isinstance(data, dict):
        return False

    changed = False

    # Strip managed hook entries.
    hooks = data.get("hooks") or {}
    if isinstance(hooks, dict):
        new_hooks: dict = {}
        for event, entries in hooks.items():
            cleaned = [e for e in entries if not is_managed_claude_hook_entry(e)]
            if len(cleaned) != len(entries):
                changed = True
            if cleaned:
                new_hooks[event] = cleaned
        if changed:
            if new_hooks:
                data["hooks"] = new_hooks
            else:
                data.pop("hooks", None)

    if not changed:
        return False
    if not dry_run:
        if data:
            settings.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        else:
            settings.unlink(missing_ok=True)
    return True


def _strip_claude_mcp(mcp_json: Path, dry_run: bool) -> bool:
    """Remove hypercharge entry from .mcp.json (repo root); delete file if empty."""
    if not mcp_json.is_file():
        return False
    try:
        data = json.loads(mcp_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    if not isinstance(data, dict):
        return False

    mcp = data.get("mcpServers") or {}
    if not isinstance(mcp, dict) or "hypercharge" not in mcp:
        return False

    mcp.pop("hypercharge")
    if mcp:
        data["mcpServers"] = mcp
    else:
        data.pop("mcpServers", None)

    if not dry_run:
        if data:
            mcp_json.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        else:
            mcp_json.unlink(missing_ok=True)
    return True


def _strip_claude_md(claude_md: Path, dry_run: bool) -> bool:
    """Remove the hypercharge-managed block from CLAUDE.md. Delete file if it becomes empty."""
    if not claude_md.is_file():
        return False
    text = claude_md.read_text(encoding="utf-8")
    pattern = re.compile(
        re.escape(_MANAGED_START) + r".*?" + re.escape(_MANAGED_END),
        flags=re.DOTALL,
    )
    if not pattern.search(text):
        return False
    new_text = pattern.sub("", text).strip()
    if not dry_run:
        if new_text:
            claude_md.write_text(new_text + "\n", encoding="utf-8")
        else:
            claude_md.unlink(missing_ok=True)
    return True


def _strip_agent_map(agent_map: Path, dry_run: bool) -> bool:
    """Remove the Hypercharge row from .cursor/rules/agent-map.mdc."""
    if not agent_map.is_file():
        return False
    text = agent_map.read_text(encoding="utf-8")
    # Match any table row that contains the managed hypercharge rule refs.
    needle = "hypercharge.mdc"
    if needle not in text:
        return False
    lines = [ln for ln in text.splitlines() if needle not in ln]
    new_text = "\n".join(lines) + "\n"
    if new_text == text:
        return False
    if not dry_run:
        agent_map.write_text(new_text, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_teardown(
    root: Path,
    console: HyperConsole,
    *,
    dry_run: bool = False,
    confirm: bool = False,
    target: str = "both",
    quiet: bool = False,
) -> int:
    """Remove all Hypercharge scaffolding from *root*.

    Reverses `hypercharge setup`.  Files that are shared with user content
    (CLAUDE.md, hooks.json, .claude/settings.json, agent-map.mdc) are
    *stripped* rather than deleted outright.

    Returns 0 on success, 1 on cancellation.
    """
    from hypercharge.agent_target import deploys_claude, deploys_cursor, normalize_agent_target

    root = root.resolve()
    target = normalize_agent_target(target)

    if not quiet:
        console.banner()

    if dry_run:
        console.warn("Dry-run mode — no files will be changed.")
    elif not confirm:
        if sys.stdin.isatty():
            console.console.print(f"\n[bold]Teardown target:[/] {target}")
            ans = input("Remove Hypercharge scaffolding for this target? [y/N]: ").strip().lower()
            if ans not in ("y", "yes"):
                console.footer("Teardown cancelled", ["No files changed."])
                return 1

    removed: list[str] = []
    stripped: list[str] = []

    # ── 1  Cursor rules ────────────────────────────────────────────────────
    if deploys_cursor(target):
        for name in _MANAGED_RULES:
            p = root / ".cursor/rules" / name
            if p.is_file():
                _remove_path(p, dry_run, removed)

    # ── 2  Cursor hook scripts ─────────────────────────────────────────────
    if deploys_cursor(target):
        hooks_dir = root / ".cursor/hooks"
        if hooks_dir.is_dir():
            for script in sorted(hooks_dir.glob("*.sh")):
                if any(script.name.startswith(pfx) for pfx in _HOOK_SCRIPT_PREFIXES):
                    _remove_path(script, dry_run, removed)

    # ── 3  hooks.json (strip, not delete) ─────────────────────────────────
    if deploys_cursor(target):
        hooks_json = root / ".cursor/hooks.json"
        if _strip_cursor_hooks(hooks_json, dry_run):
            stripped.append(str(hooks_json.relative_to(root)))

    # ── 4  .cursor/rules/agent-map.mdc (strip row) ────────────────────────
    if deploys_cursor(target):
        agent_map = root / ".cursor/rules/agent-map.mdc"
        if _strip_agent_map(agent_map, dry_run):
            stripped.append(str(agent_map.relative_to(root)))

    # ── 4b  .cursor/mcp.json (strip hypercharge entry) ────────────────────
    if deploys_cursor(target):
        cursor_mcp = root / ".cursor/mcp.json"
        if _strip_cursor_mcp(cursor_mcp, dry_run):
            stripped.append(str(cursor_mcp.relative_to(root)))

    # ── 5  Cursor skill ────────────────────────────────────────────────────
    if deploys_cursor(target):
        cursor_skill = root / ".cursor/skills/repo-guardrail"
        if cursor_skill.is_dir():
            _remove_path(cursor_skill, dry_run, removed)

    # ── 6  Claude hooks ────────────────────────────────────────────────────
    if deploys_claude(target):
        claude_hooks_dir = root / ".claude/hooks"
        if claude_hooks_dir.is_dir():
            for script in sorted(claude_hooks_dir.glob("*.sh")):
                if any(script.name.startswith(pfx) for pfx in _HOOK_SCRIPT_PREFIXES):
                    _remove_path(script, dry_run, removed)

    # ── 7  .claude/settings.json (strip hooks only) ───────────────────────
    if deploys_claude(target):
        claude_settings = root / ".claude/settings.json"
        if _strip_claude_settings(claude_settings, dry_run):
            stripped.append(str(claude_settings.relative_to(root)))

    # ── 7b  .mcp.json (strip hypercharge MCP entry) ───────────────────────
    if deploys_claude(target):
        claude_mcp = root / ".mcp.json"
        if _strip_claude_mcp(claude_mcp, dry_run):
            stripped.append(".mcp.json")

    # ── 8  CLAUDE.md managed block ────────────────────────────────────────
    if deploys_claude(target):
        claude_md = root / "CLAUDE.md"
        if _strip_claude_md(claude_md, dry_run):
            stripped.append("CLAUDE.md")

    # ── 9  Claude skill ────────────────────────────────────────────────────
    if deploys_claude(target):
        claude_skill = root / ".claude/skills/repo-guardrail"
        if claude_skill.is_dir():
            _remove_path(claude_skill, dry_run, removed)

    # ── 10  Shared scaffolding — full teardown only (`--target both`) ─────
    if target == "both":
        for rel in _HC_DIRS:
            p = root / rel
            if p.exists():
                _remove_path(p, dry_run, removed)

        for rel in _HC_FILES:
            p = root / rel
            if p.is_file():
                _remove_path(p, dry_run, removed)

        legacy_graph = root / _LEGACY_GRAPHIFY_OUT
        if legacy_graph.is_dir():
            _remove_path(legacy_graph, dry_run, removed)

    # ── Summary ───────────────────────────────────────────────────────────
    total = len(removed) + len(stripped)
    if total == 0:
        console.step_ok("Nothing to remove — repo is already clean.", 1, 1)
        return 0

    if not quiet:
        if removed:
            console.console.print("\n[bold]Removed:[/]")
            for r in removed:
                console.console.print(f"  {r}")
        if stripped:
            console.console.print("\n[bold]Stripped hypercharge content from:[/]")
            for s in stripped:
                console.console.print(f"  {s}")

    if dry_run:
        console.footer(
            f"Teardown preview ({total} items)",
            ["Re-run without --dry-run to apply."],
        )
        return 0

    console.footer(
        "Teardown complete",
        [
            f"Removed {len(removed)} file(s)/dir(s), stripped {len(stripped)} shared file(s).",
            "Hypercharge scaffolding has been removed from this repo.",
            *(
                [
                    "Partial teardown: session, graph, and repo-profile remain.",
                    "Run hypercharge teardown --target both --yes for a full clean.",
                ]
                if target != "both"
                else []
            ),
            "To re-apply, run: hypercharge setup",
        ],
    )
    return 0
