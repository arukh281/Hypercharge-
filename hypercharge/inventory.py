"""Scan rules and skills; produce inventory recommendations."""

from __future__ import annotations

from pathlib import Path

import yaml

from hypercharge.paths import CURSOR_RULES, global_skill_scan_bases
from hypercharge.skill_packs import BUNDLED_SKILL_NAMES


def _read_skill_name(skill_md: Path) -> str:
    """Internal _read_skill_name. Args: skill_md. Returns: skill_md.parent.name. (hypercharge-managed)"""
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines()[:20]:
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip()
    return skill_md.parent.name


def scan_project_inventory(root: Path) -> list[dict[str, str]]:
    """Scan project inventory. Args: root. Returns: rows. (hypercharge-managed)"""
    rows: list[dict[str, str]] = []
    rules_dir = root / CURSOR_RULES
    if rules_dir.is_dir():
        for mdc in sorted(rules_dir.glob("*.mdc")):
            name = mdc.stem
            rec = "keep"
            reason = "Project rule"
            if name.startswith("hypercharge-"):
                reason = "Hypercharge-managed (synced by setup)"
            elif name == "agent-map":
                reason = "Task router"
            rows.append(
                {
                    "name": name,
                    "type": "rule",
                    "path": str(mdc.relative_to(root)),
                    "recommendation": rec,
                    "reason": reason,
                }
            )

    skills_root = root / Path(".cursor/skills")
    if skills_root.is_dir():
        for skill_md in sorted(skills_root.glob("**/SKILL.md")):
            sname = _read_skill_name(skill_md)
            rec = "keep"
            reason = "Project skill"
            if skill_md.parent.name == "repo-guardrail":
                reason = "Hypercharge router"
            rows.append(
                {
                    "name": sname,
                    "type": "skill",
                    "path": str(skill_md.relative_to(root)),
                    "recommendation": rec,
                    "reason": reason,
                }
            )

    return rows


_KEEP_GLOBAL_SKILLS = frozenset({"graphify", "repo-guardrail"}) | frozenset(BUNDLED_SKILL_NAMES)
_SKIP_PATH_PARTS = frozenset({"cache", "plugins", ".git", "node_modules", "__pycache__"})


def _iter_global_skill_files(base: Path):
    """Skill roots only — avoid deep plugin/cache trees."""
    if not base.is_dir():
        return
    for skill_md in sorted(base.glob("*/SKILL.md")):
        if any(part in _SKIP_PATH_PARTS for part in skill_md.parts):
            continue
        yield skill_md
    if base.name == "skills-cursor":
        for skill_md in sorted(base.glob("*/skills/*/SKILL.md")):
            if any(part in _SKIP_PATH_PARTS for part in skill_md.parts):
                continue
            yield skill_md


def scan_user_skills() -> list[dict[str, str]]:
    """Global skills from Cursor (~/.cursor) and Claude Code (~/.claude), deduped by name."""
    rows: list[dict[str, str]] = []
    seen_names: set[str] = set()
    for base in global_skill_scan_bases():
        for skill_md in _iter_global_skill_files(base):
            name = _read_skill_name(skill_md)
            if name in seen_names:
                continue
            seen_names.add(name)
            host = "Claude Code" if ".claude" in skill_md.parts else "Cursor"
            if name in _KEEP_GLOBAL_SKILLS:
                rec, reason = "keep", f"Global ({host}) — keep for Hypercharge"
            else:
                rec = "review"
                reason = f"Global ({host}) — disable if not for this repo"
            rows.append(
                {
                    "name": name,
                    "type": "user skill",
                    "path": str(skill_md),
                    "recommendation": rec,
                    "reason": reason,
                }
            )
    return rows


def write_inventory_report(root: Path, rows: list[dict[str, str]]) -> Path:
    """Write inventory report. Args: root, rows. Returns: out. (hypercharge-managed)"""
    out = root / ".cursor/hypercharge/last-inventory.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Hypercharge inventory\n", f"Total items: {len(rows)}\n\n"]
    for r in rows:
        lines.append(
            f"- **{r['name']}** ({r['type']}): {r['recommendation']} — {r['reason']}\n"
        )
    out.write_text("".join(lines), encoding="utf-8")
    return out


def inventory_user_summary(rows: list[dict[str, str]]) -> list[str]:
    """Plain-language lines for terminal footer and agent chat after setup."""
    project = [r for r in rows if r.get("type") in ("rule", "skill")]
    global_skills = [r for r in rows if r.get("type") == "user skill"]
    lines = [
        f"Repo rules/skills: {len(project)} — all kept (nothing changed).",
    ]
    if global_skills:
        names = sorted({r["name"] for r in global_skills})
        preview = ", ".join(names[:8])
        extra = f" (+{len(names) - 8} more)" if len(names) > 8 else ""
        lines.append(
            f"Global skills on your machine: {len(names)} — optional cleanup."
        )
        lines.append(f"  Examples: {preview}{extra}")
        lines.append(
            "  Cursor: Settings → Cursor Settings → Rules → Skills — turn OFF unused."
        )
        lines.append(
            "  Claude Code: remove unused folders under ~/.claude/skills/ (or disable in app)."
        )
        lines.append("  Keep for this repo: graphify, hypercharge. Full list: .cursor/hypercharge/last-inventory.md")
    return lines


def load_repo_profile(root: Path) -> dict:
    """Load repo profile. Args: root. Returns: {}. (hypercharge-managed)"""
    p = root / ".cursor/repo-profile.json"
    if p.is_file():
        import json

        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def save_repo_profile(root: Path, profile: dict) -> None:
    """Save repo profile. Args: root, profile. (hypercharge-managed)"""
    import json

    p = root / ".cursor/repo-profile.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

