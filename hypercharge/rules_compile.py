"""Rules compile — analyse conflicts, propose resolutions, apply approved hardening."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from hypercharge.paths import CURSOR_RULES


@dataclass
class CompileIssue:
    id: str
    severity: str  # conflict | overlap | stale | gap
    rules: list[str]
    summary: str
    resolution: str
    auto_fix: str | None = None


@dataclass
class CompilePlan:
    generated_at: str
    issues: list[CompileIssue] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """To dict. Returns: {'generated_at': self.generated_at, 'issues': [asd. (hypercharge-managed)"""
        return {
            "generated_at": self.generated_at,
            "issues": [asdict(i) for i in self.issues],
            "actions": self.actions,
        }


def _read_rules(root: Path) -> dict[str, str]:
    """Internal _read_rules. Args: root. Returns: {p.stem: p.read_text(encoding='utf-8') for p in so. (hypercharge-managed)"""
    rules_dir = root / CURSOR_RULES
    if not rules_dir.is_dir():
        return {}
    return {p.stem: p.read_text(encoding="utf-8") for p in sorted(rules_dir.glob("*.mdc"))}


def analyse_rules(root: Path) -> CompilePlan:
    """Scan project rules for overlaps, conflicts, and gaps."""
    root = root.resolve()
    rules = _read_rules(root)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    plan = CompilePlan(generated_at=now)

    if not rules:
        plan.issues.append(
            CompileIssue(
                id="no-rules",
                severity="gap",
                rules=[],
                summary="No .cursor/rules/*.mdc files found",
                resolution="Run hypercharge setup first",
            )
        )
        return plan

    venv = rules.get("venv-activation", "")
    if venv and "hypercharge" not in venv.lower():
        plan.issues.append(
            CompileIssue(
                id="venv-scope",
                severity="conflict",
                rules=["venv-activation", "hypercharge onboard"],
                summary="Python venv rule does not list hypercharge/.venv",
                resolution=(
                    "hypercharge CLI + graphify (slim, on setup) → hypercharge/.venv; "
                    "other Python work → that project's own .venv"
                ),
                auto_fix="hypercharge-rules-compile",
            )
        )

    if "direct-chat-style" in rules:
        plan.issues.append(
            CompileIssue(
                id="style-overlap",
                severity="overlap",
                rules=["direct-chat-style", "communication preferences"],
                summary="Short plain sentences vs longer complete prose in user prefs",
                resolution=(
                    "Write clear complete sentences in plain English; avoid buzzwords unless the user asks"
                ),
                auto_fix="hypercharge-rules-compile",
            )
        )

    if "readme-creation" in rules:
        plan.issues.append(
            CompileIssue(
                id="markdown-scope",
                severity="overlap",
                rules=["readme-creation", "hypercharge setup/onboard/compile"],
                summary="Ask-before-markdown vs Hypercharge writing reports during setup",
                resolution=(
                    "Ask before new user-facing docs; Hypercharge may write "
                    ".cursor/hypercharge/*, .cursor/graphify-out/*, and compile outputs when the user approves compile"
                ),
                auto_fix="hypercharge-rules-compile",
            )
        )

    if "high-volume-changes" in rules:
        plan.issues.append(
            CompileIssue(
                id="volume-onboard",
                severity="overlap",
                rules=["high-volume-changes", "hypercharge onboard/setup"],
                summary="Confirm-before-bulk vs automated onboard touching many files",
                resolution=(
                    "User saying install hypercharge / onboard / compile pre-approves that flow; "
                    "all other wide refactors still need explicit confirmation"
                ),
                auto_fix="hypercharge-rules-compile",
            )
        )


    agent_map = rules.get("agent-map", "")
    if agent_map:
        if "hypercharge.mdc" not in agent_map and "hypercharge-grounding.mdc" not in agent_map:
            plan.issues.append(
                CompileIssue(
                    id="agent-map-hypercharge",
                    severity="gap",
                    rules=["agent-map", "hypercharge"],
                    summary="Hypercharge managed rules missing from agent-map router",
                    resolution="Add Hypercharge row to agent-map.mdc (hypercharge.mdc + hypercharge-grounding.mdc)",
                    auto_fix="agent-map",
                )
            )
        if "hypercharge-rules-compile" not in agent_map:
            plan.issues.append(
                CompileIssue(
                    id="agent-map-compile",
                    severity="gap",
                    rules=["agent-map"],
                    summary="No router entry for rule precedence after compile",
                    resolution="Add rules-compile precedence row to agent-map.mdc",
                    auto_fix="agent-map",
                )
            )

    plan.actions = _planned_actions(plan)
    return plan


def _planned_actions(plan: CompilePlan) -> list[str]:
    """Internal _planned_actions. Args: plan. Returns: actions. (hypercharge-managed)"""
    actions: list[str] = []
    if any(i.auto_fix == "hypercharge-rules-compile" for i in plan.issues):
        actions.append("Create .cursor/rules/hypercharge-rules-compile.mdc (precedence + conflict resolutions)")
    if any(i.auto_fix == "agent-map" for i in plan.issues):
        actions.append("Update .cursor/rules/agent-map.mdc (router rows for Hypercharge + compile)")
    actions.append("Write .cursor/hypercharge/compile-plan.json and compile-report.md")
    actions.append("Mark rules-compile complete")
    return actions


def _render_precedence_rule(plan: CompilePlan) -> str:
    """Internal _render_precedence_rule. Args: plan. Returns: '\n'.join(lines).rstrip() + '\n'. (hypercharge-managed)"""
    lines = [
        "---",
        "description: Rule precedence and conflict resolutions (Hypercharge rules compile)",
        "alwaysApply: true",
        "---",
        "",
        "# Rules compile · precedence",
        "",
        "<!-- hypercharge-rules-compile: generated by `hypercharge compile` — edit via re-running compile -->",
        "",
        "When project rules disagree, follow this order:",
        "",
        "1. **User message in this chat** (latest instruction wins)",
        "2. **Hypercharge managed rules** (`hypercharge`, `hypercharge-grounding`) for session + grounding",
        "3. **This file** for cross-rule conflicts listed below",
        "4. **Other always-apply project rules**",
        "5. **On-demand rules** loaded via agent-map",
        "",
        "## Resolutions",
        "",
    ]
    for issue in plan.issues:
        if issue.severity == "stale":
            continue
        rules_s = " + ".join(f"`{r}`" for r in issue.rules)
        lines.append(f"### {issue.id}")
        lines.append(f"- **Rules:** {rules_s}")
        lines.append(f"- **Issue:** {issue.summary}")
        lines.append(f"- **Do this:** {issue.resolution}")
        lines.append("")

    lines.extend(
        [
            "## Python environments",
            "",
            "| Work | Venv |",
            "|------|------|",
            "| `hypercharge`, `graphify` (slim stack) | `hypercharge/.venv` |",
            "| Other Python work | that project's own `.venv` |",
            "",
            "Never use the system Python when a row above applies.",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _patch_agent_map(root: Path, plan: CompilePlan) -> bool:
    """Internal _patch_agent_map. Args: root, plan. Returns: changed. (hypercharge-managed)"""
    path = root / CURSOR_RULES / "agent-map.mdc"
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    changed = False
    rows: list[str] = []
    if "hypercharge.mdc" not in text:
        rows.append(
            "| Hypercharge (every turn) | `hypercharge.mdc`, `hypercharge-grounding.mdc` — synced by setup |"
        )
    if "hypercharge-rules-compile" not in text:
        rows.append("| Rule conflicts / precedence | `hypercharge-rules-compile.mdc` |")
    if not rows:
        return False
    block = "\n".join(rows) + "\n\n"
    needle = "Disable global skills"
    if needle in text:
        text = text.replace(needle, block + needle, 1)
        changed = True
    else:
        text = text.rstrip() + "\n" + block
        changed = True
    if changed:
        if "hypercharge-compile-synced" not in text:
            text = text.rstrip() + "\n\n<!-- hypercharge-compile-synced -->\n"
        path.write_text(text, encoding="utf-8")
    return changed


def write_compile_artifacts(root: Path, plan: CompilePlan) -> tuple[Path, Path]:
    """Write compile artifacts. Args: root, plan. Returns: (plan_path, report_path). (hypercharge-managed)"""
    out_dir = root / ".cursor/hypercharge"
    out_dir.mkdir(parents=True, exist_ok=True)
    plan_path = out_dir / "compile-plan.json"
    plan_path.write_text(json.dumps(plan.to_dict(), indent=2) + "\n", encoding="utf-8")

    report_path = out_dir / "compile-report.md"
    lines = [
        "# Rules compile report\n",
        f"Generated: {plan.generated_at}\n\n",
        "## Planned actions\n",
    ]
    for a in plan.actions:
        lines.append(f"- {a}\n")
    lines.append("\n## Issues found\n\n")
    for issue in plan.issues:
        lines.append(f"### {issue.id} ({issue.severity})\n")
        lines.append(f"- **Rules:** {', '.join(issue.rules) or '—'}\n")
        lines.append(f"- **Summary:** {issue.summary}\n")
        lines.append(f"- **Resolution:** {issue.resolution}\n\n")
    report_path.write_text("".join(lines), encoding="utf-8")
    return plan_path, report_path


def apply_compile_plan(root: Path, plan: CompilePlan) -> list[str]:
    """Apply approved hardening. Does not rewrite user-owned rules (except agent-map patches)."""
    root = root.resolve()
    applied: list[str] = []

    if any(i.auto_fix == "hypercharge-rules-compile" for i in plan.issues):
        rule_path = root / CURSOR_RULES / "hypercharge-rules-compile.mdc"
        rule_path.write_text(_render_precedence_rule(plan), encoding="utf-8")
        applied.append(str(rule_path.relative_to(root)))

    if _patch_agent_map(root, plan):
        applied.append(".cursor/rules/agent-map.mdc")

    write_compile_artifacts(root, plan)
    applied.append(".cursor/hypercharge/compile-plan.json")
    applied.append(".cursor/hypercharge/compile-report.md")
    return applied


def plan_summary_lines(plan: CompilePlan) -> list[str]:
    """Plain-language bullets for agent chat before/after compile."""
    lines = ["**Rules compile will:**"]
    for action in plan.actions:
        lines.append(f"- {action}")
    if plan.issues:
        lines.append("")
        lines.append(f"**Found {len(plan.issues)} issue(s):**")
        for issue in plan.issues:
            lines.append(f"- {issue.summary}")
    return lines
