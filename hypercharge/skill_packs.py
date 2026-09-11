"""Bundled agent skills — shipped inside the hypercharge package (no web fetch)."""

from __future__ import annotations

import shutil
from pathlib import Path

from hypercharge.paths import PACKAGE_ROOT, agent_skill_install_dirs

SKILL_PACKS_ROOT = PACKAGE_ROOT / "skill-packs"
MAIN_SKILL_SRC = PACKAGE_ROOT / "skill" / "hypercharge"

# Order: main playbook first, then core pack (install overwrites by name).
BUNDLED_SKILL_NAMES: tuple[str, ...] = (
    "hypercharge",
    "hypercharge-concise",
    "ask-questions-if-underspecified",
    "differential-review",
    "insecure-defaults",
    "static-analysis",
    "modern-python",
    "test-driven-development",
    "systematic-debugging",
    "verification-before-completion",
)

# Lean install for Claude Code — fewer overlapping packs.
CLAUDE_MINIMAL_SKILL_NAMES: tuple[str, ...] = (
    "hypercharge",
    "hypercharge-concise",
    "systematic-debugging",
)


def bundled_skill_src(name: str) -> Path | None:
    if name == "hypercharge":
        return MAIN_SKILL_SRC if MAIN_SKILL_SRC.is_dir() else None
    pack = SKILL_PACKS_ROOT / name
    if (pack / "SKILL.md").is_file():
        return pack
    return None


def list_bundled_skills(*, target: str = "both") -> list[tuple[str, Path]]:
    from hypercharge.agent_target import normalize_agent_target

    names = (
        CLAUDE_MINIMAL_SKILL_NAMES
        if normalize_agent_target(target) == "claude"
        else BUNDLED_SKILL_NAMES
    )
    out: list[tuple[str, Path]] = []
    for name in names:
        src = bundled_skill_src(name)
        if src is not None:
            out.append((name, src))
    return out


def sync_bundled_skills(*, target: str = "both") -> tuple[int, list[str]]:
    """Install bundled skills to agent global skill dirs. Returns (count, names)."""
    skills = list_bundled_skills(target=target)
    if not skills:
        return 0, []
    from hypercharge.agent_target import deploys_claude, deploys_cursor, normalize_agent_target

    target = normalize_agent_target(target)
    install_dirs: list[tuple[str, Path]] = []
    if deploys_cursor(target):
        install_dirs.append(("Cursor", agent_skill_install_dirs()[0][1]))
    if deploys_claude(target):
        install_dirs.append(("Claude Code", agent_skill_install_dirs()[1][1]))
    for _, dest_parent in install_dirs:
        dest_parent.parent.mkdir(parents=True, exist_ok=True)
        for name, src in skills:
            dest = dest_parent.parent / name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
    return len(skills), [n for n, _ in skills]
