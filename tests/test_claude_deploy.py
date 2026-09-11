"""Claude Code deploy — CLAUDE.md contract, project skill, target flag."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from hypercharge.claude_deploy import (
    MANAGED_END,
    MANAGED_START,
    deploy_claude_contract,
    sync_claude_md,
)
from hypercharge.doctor_cmd import build_doctor_report, _doctor_exit_code
from hypercharge.templates_deploy import deploy_templates


def test_claude_target_deploys_contract_not_cursor_rules():
    """Test claude target deploys contract not cursor rules. (hypercharge-managed)"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        touched = deploy_templates(root, target="claude")
        assert not (root / ".cursor/rules/hypercharge.mdc").is_file()
        assert not (root / ".cursor/hooks.json").is_file()
        assert (root / ".claude/settings.json").is_file()
        assert (root / ".claude/skills/repo-guardrail/SKILL.md").is_file()
        assert (root / "CLAUDE.md").is_file()
        assert MANAGED_START in (root / "CLAUDE.md").read_text(encoding="utf-8")
        assert any("CLAUDE.md" in p for p in touched)


def test_claude_md_block_replaced_on_resync():
    """Test claude md block replaced on resync. (hypercharge-managed)"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "CLAUDE.md").write_text(
            f"# Hi\n\n{MANAGED_START}\nold\n{MANAGED_END}\n",
            encoding="utf-8",
        )
        sync_claude_md(root)
        text = (root / "CLAUDE.md").read_text(encoding="utf-8")
        block = text.split(MANAGED_START, 1)[1].split(MANAGED_END, 1)[0]
        assert not any(ln.strip() == "old" for ln in block.splitlines())
        assert "Hypercharge" in text


def test_doctor_claude_target_skips_cursor_rules():
    """Test doctor claude target skips cursor rules. (hypercharge-managed)"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        deploy_templates(root, target="claude")
        report = build_doctor_report(root)
        assert report["agent_target"] == "claude"
        assert report["managed_rules_ok"] is True
        assert report["claude_contract_ok"] is True
        assert _doctor_exit_code(report, tier="ready") == 0


def test_repo_profile_records_agent_target():
    """Test repo profile records agent target. (hypercharge-managed)"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        deploy_templates(root, target="claude")
        profile = json.loads((root / ".cursor/repo-profile.json").read_text(encoding="utf-8"))
        assert profile["agent_target"] == "claude"


def test_deploy_claude_contract_idempotent():
    """Test deploy claude contract idempotent. (hypercharge-managed)"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        first = deploy_claude_contract(root)
        second = deploy_claude_contract(root)
        assert first
        assert not second or second == []
