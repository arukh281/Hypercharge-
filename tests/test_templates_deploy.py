"""Template deploy correctness."""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypercharge.templates_deploy import deploy_templates


def test_repo_guardrail_skill_not_main_playbook():
    """Test repo guardrail skill not main playbook. (hypercharge-managed)"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        deploy_templates(root)
        skill = (root / ".cursor/skills/repo-guardrail/SKILL.md").read_text(encoding="utf-8")
        assert "name: repo-guardrail" in skill or "Repo guardrail" in skill
        assert "Golden rule" not in skill
        assert "hypercharge.mdc" in skill
        assert "hypercharge-grounding.mdc" in skill
