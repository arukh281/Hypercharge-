"""Claude Code repo wiring — CLAUDE.md contract + project skills."""

from __future__ import annotations

import json
import re
from pathlib import Path

from hypercharge.paths import PACKAGE_ROOT

TEMPLATES = PACKAGE_ROOT / "templates"
CLAUDE_BLOCK_TEMPLATE = TEMPLATES / "CLAUDE-hypercharge-block.md"
CLAUDE_SKILL_TEMPLATE = TEMPLATES / "claude-repo-guardrail-SKILL.md"

MANAGED_START = "<!-- hypercharge-managed:start -->"
MANAGED_END = "<!-- hypercharge-managed:end -->"


def build_claude_contract_block() -> str:
    """Managed Hypercharge contract for CLAUDE.md."""
    if CLAUDE_BLOCK_TEMPLATE.is_file():
        body = CLAUDE_BLOCK_TEMPLATE.read_text(encoding="utf-8").strip()
    else:
        body = "# Hypercharge\n\nRun `hypercharge query` before repo claims. Say **wrap up** at session end."
    return f"{MANAGED_START}\n{body}\n{MANAGED_END}"


def sync_claude_md(root: Path) -> bool:
    """Merge managed block into repo CLAUDE.md. Returns True if written."""
    root = root.resolve()
    dest = root / "CLAUDE.md"
    block = build_claude_contract_block()

    if dest.is_file():
        text = dest.read_text(encoding="utf-8")
        pattern = re.compile(
            re.escape(MANAGED_START) + r".*?" + re.escape(MANAGED_END),
            flags=re.DOTALL,
        )
        if pattern.search(text):
            new_text = pattern.sub(block, text, count=1)
        else:
            sep = "\n\n" if text.endswith("\n") or not text.strip() else "\n\n"
            new_text = text.rstrip() + sep + block + "\n"
        if new_text == text:
            return False
        dest.write_text(new_text, encoding="utf-8")
        return True

    dest.write_text(
        "# Project\n\n"
        "This repo uses **Hypercharge** for grounded agent work.\n\n"
        f"{block}\n",
        encoding="utf-8",
    )
    return True


def deploy_claude_repo_skill(root: Path) -> bool:
    """Deploy `.claude/skills/repo-guardrail/SKILL.md`. Returns True if written."""
    if not CLAUDE_SKILL_TEMPLATE.is_file():
        return False
    dest = root / ".claude/skills/repo-guardrail/SKILL.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    src_text = CLAUDE_SKILL_TEMPLATE.read_text(encoding="utf-8")
    if dest.is_file() and dest.read_text(encoding="utf-8") == src_text:
        return False
    dest.write_text(src_text, encoding="utf-8")
    return True


def claude_contract_health(root: Path) -> list[str]:
    """Return issues if Claude contract is missing."""
    issues: list[str] = []
    claude_md = root / "CLAUDE.md"
    skill = root / ".claude/skills/repo-guardrail/SKILL.md"
    md_ok = False
    if claude_md.is_file():
        try:
            md_ok = MANAGED_START in claude_md.read_text(encoding="utf-8")
        except OSError:
            md_ok = False
    if not md_ok and not skill.is_file():
        issues.append("claude_contract_missing")
    if not skill.is_file():
        issues.append("claude_repo_skill_missing")
    if claude_md.is_file() and not md_ok:
        issues.append("claude_md_block_missing")
    return issues


def register_mcp_server(root: Path) -> bool:
    """Merge hypercharge MCP server entry into .mcp.json (repo root).

    Returns True if the file was changed, False if already up to date.
    """
    root = root.resolve()
    mcp_path = root / ".mcp.json"

    if mcp_path.is_file():
        try:
            config: dict = json.loads(mcp_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # Preserve a hand-written but malformed file (back it up) rather than
            # silently discarding whatever other servers it may declare.
            try:
                mcp_path.replace(mcp_path.with_name(mcp_path.name + ".bak"))
            except OSError:
                pass
            config = {}
    else:
        config = {}

    desired_entry = {
        "type": "stdio",
        "command": "hypercharge",
        "args": ["mcp-server", "--repo", str(root)],
        "env": {},
    }

    mcp_servers = config.setdefault("mcpServers", {})
    if mcp_servers.get("hypercharge") == desired_entry:
        return False

    mcp_servers["hypercharge"] = desired_entry
    mcp_path.parent.mkdir(parents=True, exist_ok=True)
    mcp_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return True


def register_cursor_mcp_server(root: Path) -> bool:
    """Merge hypercharge MCP server entry into .cursor/mcp.json.

    Returns True if the file was changed, False if already up to date.
    """
    root = root.resolve()
    mcp_path = root / ".cursor/mcp.json"

    if mcp_path.is_file():
        try:
            config: dict = json.loads(mcp_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            config = {}
    else:
        config = {}

    desired_entry = {
        "type": "stdio",
        "command": "hypercharge",
        "args": ["mcp-server", "--repo", str(root)],
        "env": {},
    }

    mcp_servers = config.setdefault("mcpServers", {})
    if mcp_servers.get("hypercharge") == desired_entry:
        return False

    mcp_servers["hypercharge"] = desired_entry
    mcp_path.parent.mkdir(parents=True, exist_ok=True)
    mcp_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return True


def deploy_claude_contract(root: Path) -> list[str]:
    """Sync CLAUDE.md block + project skill + MCP server entry. Returns relative paths touched."""
    touched: list[str] = []
    if sync_claude_md(root):
        touched.append("CLAUDE.md")
    if deploy_claude_repo_skill(root):
        touched.append(".claude/skills/repo-guardrail/SKILL.md")
    if register_mcp_server(root):
        touched.append(".mcp.json")
    return touched
