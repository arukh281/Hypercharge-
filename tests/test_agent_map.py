"""agent-map deduplication on setup."""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypercharge.templates_deploy import deploy_templates


def test_agent_map_dedupes_legacy_row():
    """Test agent map dedupes legacy row. (hypercharge-managed)"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        rules = root / ".cursor/rules"
        rules.mkdir(parents=True)
        (rules / "agent-map.mdc").write_text(
            "---\nalwaysApply: false\n---\n\n# Agent map\n\n"
            "| Task | Load |\n|------|------|\n"
            "| Hypercharge (every turn) | "
            "`hypercharge.mdc`, `hypercharge-grounding.mdc` |\n"
            "| Hypercharge graph + session (every turn) | "
            "`hypercharge.mdc` — synced by setup |\n",
            encoding="utf-8",
        )
        deploy_templates(root)
        text = (rules / "agent-map.mdc").read_text(encoding="utf-8")
        assert text.count("Hypercharge graph + session") == 0
        assert "hypercharge-grounding.mdc" in text
