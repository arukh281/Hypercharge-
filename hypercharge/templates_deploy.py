"""Deploy repo templates — Hypercharge-managed rules always sync on setup."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from hypercharge import __version__
from hypercharge.agent_target import deploys_claude, deploys_cursor, normalize_agent_target
from hypercharge.claude_deploy import deploy_claude_contract, register_cursor_mcp_server
from hypercharge.hooks_deploy import deploy_hooks
from hypercharge.claude_hooks_deploy import deploy_claude_hooks
from hypercharge.paths import PACKAGE_ROOT, REPO_GUARDRAIL_SKILL_SRC

TEMPLATES = PACKAGE_ROOT / "templates"

# Always overwritten on every `hypercharge setup` (repo contract).
MANAGED_RULES = (
    "hypercharge.mdc",
    "hypercharge-grounding.mdc",
)

# Retired Hypercharge rules — removed on setup if present.
RETIRED_MANAGED_RULES = (
    "hypercharge-runtime.mdc",
    "hypercharge-autocontext.mdc",
    "hypercharge-live-context.mdc",
    "hypercharge-graphify.mdc",
    "hypercharge-session.mdc",
    "hypercharge-escalation.mdc",
    "hypercharge-enforcement.mdc",
    "hypercharge-commit-policy.mdc",
    "hypercharge-session-notes.mdc",
    "hypercharge-docs-conventions.mdc",
)

MANAGED_ALWAYS_APPLY = list(MANAGED_RULES)

MANAGED_MARKER = "hypercharge-managed"


def _copy_if_missing(src: Path, dest: Path) -> bool:
    """Internal _copy_if_missing. Args: src, dest. Returns: True. (hypercharge-managed)"""
    if dest.exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return True


def _sync_managed(src: Path, dest: Path) -> bool:
    """Copy template to dest; return True if written."""
    if not src.is_file():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return True


def _sync_repo_profile(root: Path, org: str, *, target: str = "both") -> None:
    """Internal _sync_repo_profile. Args: root, org. (hypercharge-managed)"""
    profile_path = root / ".cursor/repo-profile.json"
    if profile_path.is_file():
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    else:
        template = TEMPLATES / "repo-profile.json"
        profile = json.loads(template.read_text(encoding="utf-8")) if template.is_file() else {}

    profile["org"] = org
    profile["hypercharge_version"] = __version__
    profile["agent_target"] = normalize_agent_target(target)
    profile.setdefault("rules", {})
    if isinstance(profile["rules"], dict):
        profile["rules"]["always_apply"] = list(MANAGED_ALWAYS_APPLY)
    profile.setdefault("graph", {})
    if isinstance(profile["graph"], dict):
        graph_defaults = {
            "output_dir": ".cursor/graphify-out",
            "path": ".cursor/graphify-out/graph.json",
            "html": ".cursor/graphify-out/graph.html",
            "tree_html": ".cursor/graphify-out/GRAPH_TREE.html",
            "report": ".cursor/graphify-out/GRAPH_REPORT.md",
            "stale_after_days": 14,
        }
        for key, value in graph_defaults.items():
            current = profile["graph"].get(key, "")
            if key == "stale_after_days":
                profile["graph"].setdefault(key, value)
            elif not current or str(current).startswith("graphify-out") or not str(current).startswith(".cursor/"):
                # Rewrite bare/legacy/escaped paths to always live under .cursor/
                profile["graph"][key] = value
            else:
                profile["graph"].setdefault(key, value)
    profile.setdefault("escalation", {})
    if isinstance(profile["escalation"], dict):
        from hypercharge.escalation import (
            CLAUDE_REASONING_POOL,
            DEFAULT_REASONING_POOL,
            ESCALATION_TRIGGERS,
        )

        profile["escalation"].setdefault("auto_suggest", True)
        profile["escalation"].setdefault("mode", "ask")
        pool = (
            CLAUDE_REASONING_POOL
            if normalize_agent_target(target) == "claude"
            else DEFAULT_REASONING_POOL
        )
        profile["escalation"].setdefault("reasoning_pool", pool)
        profile["escalation"].setdefault("triggers", ESCALATION_TRIGGERS)
    template = TEMPLATES / "repo-profile.json"
    if template.is_file():
        template_profile = json.loads(template.read_text(encoding="utf-8"))
        for section in ("autonomy", "hooks", "gates", "organism"):
            tpl = template_profile.get(section)
            if not isinstance(tpl, dict):
                continue
            profile.setdefault(section, {})
            if isinstance(profile.get(section), dict):
                for key, value in tpl.items():
                    profile[section].setdefault(key, value)
        if isinstance(profile.get("autonomy"), dict):
            from hypercharge.grounding_session import is_hypercharge_source_repo

            if is_hypercharge_source_repo(root):
                profile["autonomy"]["dev_repo"] = True
                profile["autonomy"]["grounding_gate"] = "warn"
            else:
                # Advisory by default — hooks inform, they don't block. Enforcement is
                # the host (Claude Code / Cursor) permission system's job; a repo can
                # opt into `block` to have the Cursor pre-tool hook deny ungrounded writes.
                profile["autonomy"]["grounding_gate"] = "warn"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")


def _patch_agent_map(root: Path) -> bool:
    """Ensure agent-map lists Hypercharge managed rules (additive line)."""
    dest = root / ".cursor/rules/agent-map.mdc"
    src = TEMPLATES / "agent-map.mdc"
    if not src.is_file():
        return False
    if not dest.is_file():
        shutil.copy2(src, dest)
        return True
    text = dest.read_text(encoding="utf-8")
    needle = "hypercharge.mdc"
    legacy_row = "| Hypercharge graph + session (every turn) |"
    if legacy_row in text and needle in text:
        lines = [ln for ln in text.splitlines() if legacy_row not in ln]
        dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True
    if needle in text and "hypercharge-grounding.mdc" in text:
        return False
    row = (
        "| Hypercharge (every turn) | "
        "`hypercharge.mdc`, `hypercharge-grounding.mdc` — synced by setup |\n"
    )
    if "| Task |" in text or "|------|" in text:
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if line.strip().startswith("|") and "Task" in line and i + 1 < len(lines):
                lines.insert(i + 2, row.rstrip())
                dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
                return True
    return False


def deploy_templates(
    root: Path,
    org: str = "yourco",
    *,
    target: str = "both",
    advisory_skip: tuple[str, ...] = (),
) -> list[str]:
    """
    Deploy session scaffolding (additive) and sync Hypercharge-managed rules (overwrite).

    Returns paths touched relative to repo root.
    """
    _ = advisory_skip  # legacy kwarg — advisory rules no longer deployed
    touched: list[str] = []
    target = normalize_agent_target(target)
    rules_dir = root / ".cursor/rules"

    if deploys_cursor(target):
        for name in MANAGED_RULES:
            dest = rules_dir / name
            if _sync_managed(TEMPLATES / name, dest):
                touched.append(str(dest.relative_to(root)))

        for old in RETIRED_MANAGED_RULES:
            stale = rules_dir / old
            if stale.is_file():
                stale.unlink()
                touched.append(f"(removed) {stale.relative_to(root)}")

        # Legacy hypercharge grounding stub only (not project-owned grounding.mdc)
        legacy_grounding = rules_dir / "grounding.mdc"
        if legacy_grounding.is_file():
            try:
                if MANAGED_MARKER in legacy_grounding.read_text(encoding="utf-8"):
                    legacy_grounding.unlink()
                    touched.append(f"(removed) {legacy_grounding.relative_to(root)}")
            except OSError:
                pass

        bundled_skill = REPO_GUARDRAIL_SKILL_SRC / "SKILL.md"
        if bundled_skill.is_file():
            skill_dest = root / ".cursor/skills/repo-guardrail/SKILL.md"
            skill_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(bundled_skill, skill_dest)
            touched.append(str(skill_dest.relative_to(root)))

    additive = {
        "REPO_SESSION.md": root / ".cursor/session/REPO_SESSION.md",
        "OPEN_CHATS.yaml": root / ".cursor/session/OPEN_CHATS.yaml",
        "REPO_USER_PREFS.yaml": root / ".cursor/session/REPO_USER_PREFS.yaml",
    }
    for name, dest in additive.items():
        src = TEMPLATES / name
        if src.is_file() and _copy_if_missing(src, dest):
            touched.append(str(dest.relative_to(root)))

    _sync_repo_profile(root, org, target=target)
    touched.append(".cursor/repo-profile.json")

    if deploys_cursor(target) and _patch_agent_map(root):
        touched.append(".cursor/rules/agent-map.mdc")

    if deploys_cursor(target):
        touched.extend(deploy_hooks(root))
        if register_cursor_mcp_server(root):
            touched.append(".cursor/mcp.json")

    if deploys_claude(target):
        touched.extend(deploy_claude_hooks(root))
        touched.extend(deploy_claude_contract(root))

    stale_live = root / ".cursor/hypercharge/LIVE_CONTEXT.md"
    if stale_live.is_file():
        stale_live.unlink()
        touched.append("(removed) .cursor/hypercharge/LIVE_CONTEXT.md")

    lock = root / ".cursor/hypercharge.lock"
    if not lock.is_file():
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text(
            f"hypercharge_version: {__version__}\nschema_version: 1\n",
            encoding="utf-8",
        )
        touched.append(str(lock.relative_to(root)))

    return touched
