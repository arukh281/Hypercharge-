"""Subagent escalation policy — ask user before higher-reasoning help."""

from __future__ import annotations

import json
from pathlib import Path

from hypercharge.session import load_repo_profile_json

DEFAULT_REASONING_POOL: list[dict[str, str]] = [
    {
        "id": "explore",
        "label": "Explore the codebase",
        "subagent_type": "explore",
        "when": "Large or unfamiliar area; need a map before changing code",
    },
    {
        "id": "generalPurpose",
        "label": "Deep multi-step reasoning",
        "subagent_type": "generalPurpose",
        "when": "Architecture, refactor, root-cause debug, many files",
    },
    {
        "id": "shell",
        "label": "Shell / CI specialist",
        "subagent_type": "shell",
        "when": "Git, builds, test runners, environment issues",
    },
    {
        "id": "security-review",
        "label": "Security review",
        "subagent_type": "security-review",
        "when": "Auth, secrets, user input, sensitive features",
    },
    {
        "id": "bugbot",
        "label": "Code review",
        "subagent_type": "bugbot",
        "when": "Review local changes before merge",
    },
]

CLAUDE_REASONING_POOL: list[dict[str, str]] = [
    {
        "id": "explore",
        "label": "Explore the codebase",
        "when": "Large or unfamiliar area; need a map before changing code",
    },
    {
        "id": "architecture",
        "label": "Architecture / refactor reasoning",
        "when": "Trade-offs, many modules, or structural change",
    },
    {
        "id": "debug",
        "label": "Root-cause debugging",
        "when": "Same bug or test failed twice; need systematic isolation",
    },
    {
        "id": "security",
        "label": "Security review",
        "when": "Auth, secrets, user input, sensitive features",
    },
    {
        "id": "review",
        "label": "Change review",
        "when": "Review local diff before merge or handoff",
    },
]

ESCALATION_TRIGGERS: list[str] = [
    "Task spans many modules and you lack grounded context after hypercharge query + graphify update",
    "Architecture or trade-off decision with no clear single-file answer",
    "Two failed attempts on the same bug or test failure",
    "User explicitly asks for deeper thinking, review, or a second pair of eyes",
    "Security-sensitive change (auth, secrets, payments, untrusted input)",
    "Large refactor touching more than five files (see repo-profile gates.large_change_files)",
]


def load_escalation_policy(root: Path) -> dict:
    from hypercharge.agent_target import load_agent_target

    profile = load_repo_profile_json(root)
    esc = profile.get("escalation") or {}
    if not isinstance(esc, dict):
        esc = {}
    pool = esc.get("reasoning_pool")
    if not pool:
        pool = (
            CLAUDE_REASONING_POOL
            if load_agent_target(root) == "claude"
            else list(DEFAULT_REASONING_POOL)
        )
    return {
        "auto_suggest": bool(esc.get("auto_suggest", True)),
        "mode": str(esc.get("mode", "ask")),  # ask | off
        "reasoning_pool": pool,
        "triggers": list(esc.get("triggers") or ESCALATION_TRIGGERS),
    }


def escalation_enabled(root: Path) -> bool:
    policy = load_escalation_policy(root)
    return policy["auto_suggest"] and policy["mode"] != "off"


def pick_subagent_hint(task_kind: str, policy: dict | None = None) -> dict[str, str]:
    """Best-effort subagent recommendation from task kind keywords."""
    pool = (policy or {}).get("reasoning_pool") or DEFAULT_REASONING_POOL
    kind = task_kind.lower()
    if any(w in kind for w in ("security", "auth", "secret", "credential")):
        return _find(pool, "security-review")
    if any(w in kind for w in ("test", "ci", "build", "git", "shell")):
        return _find(pool, "shell")
    if any(w in kind for w in ("explore", "find", "where", "map", "structure")):
        return _find(pool, "explore")
    if any(w in kind for w in ("review", "diff", "pr")):
        return _find(pool, "bugbot")
    return _find(pool, "generalPurpose")


def _find(pool: list[dict], subagent_type: str) -> dict[str, str]:
    for row in pool:
        if row.get("subagent_type") == subagent_type or row.get("id") == subagent_type:
            return row
    return pool[0] if pool else DEFAULT_REASONING_POOL[0]


def format_escalation_brief(root: Path, *, task_hint: str = "") -> str:
    """Plain-text brief for agents (also used by CLI)."""
    from hypercharge.agent_target import load_agent_target

    policy = load_escalation_policy(root)
    is_claude = load_agent_target(root) == "claude"
    lines = [
        "# Hypercharge escalation",
        "",
        f"Enabled: {'yes' if escalation_enabled(root) else 'no'} (mode={policy['mode']})",
        "",
        "## Protocol",
    ]
    if is_claude:
        lines += [
            "1. If a trigger matches, **ask the user once** before spawning a sub-agent.",
            "2. User **yes** → spawn a focused Claude sub-agent with a clear prompt.",
            "3. User **no** → continue in this session; step through with hypercharge query + reads.",
            "4. **Never** auto-spawn without approval.",
        ]
    else:
        lines += [
            "1. If a trigger matches, **ask the user once** before launching a subagent.",
            "2. User **yes** → Task tool with the recommended subagent_type.",
            "3. User **no** → continue in this chat; use the current model's best reasoning.",
            "4. **Never** auto-launch a subagent without approval.",
        ]
    lines += ["", "## Triggers"]
    for t in policy["triggers"]:
        lines.append(f"- {t}")
    lines.append("")
    lines.append("## Reasoning pool")
    for row in policy["reasoning_pool"]:
        if is_claude:
            lines.append(f"- **{row.get('label', row.get('id'))}** — {row.get('when', '')}")
        else:
            lines.append(
                f"- **{row.get('label', row.get('id'))}** (`{row.get('subagent_type', '?')}`) — {row.get('when', '')}"
            )
    if task_hint:
        hint = pick_subagent_hint(task_hint, policy)
        lines += [
            "",
            "## Suggested for current task",
        ]
        if is_claude:
            lines.append(f"- {hint.get('label')} — {hint.get('when', '')}")
        else:
            lines.append(
                f"- {hint.get('label')} → subagent_type `{hint.get('subagent_type')}`"
            )
    return "\n".join(lines).rstrip() + "\n"
