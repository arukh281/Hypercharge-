"""Escalation policy brief for agents."""

from __future__ import annotations

from pathlib import Path

from hypercharge.escalation import format_escalation_brief
from hypercharge.ui.console import HyperConsole


def run_escalation(root: Path, console: HyperConsole, *, task_hint: str = "") -> int:
    root = root.resolve()
    if not (root / ".cursor").is_dir():
        console.step_fail("Escalation", "Run hypercharge setup in this repo first.")
        return 1
    print(format_escalation_brief(root, task_hint=task_hint))
    return 0
