"""Memory and context packet tests."""

from __future__ import annotations

from pathlib import Path

from hypercharge.context_packet_cmd import build_context_packet
from hypercharge.log_cmd import run_log
from hypercharge.session import append_decision
from hypercharge.ui.console import HyperConsole


def _minimal_setup(root: Path) -> None:
    """Internal _minimal_setup. Args: root. (hypercharge-managed)"""
    (root / ".cursor/session/chats").mkdir(parents=True)
    (root / ".cursor/session/REPO_SESSION.md").write_text(
        "# Repo session\n\n## Decisions\n\n## Activity\n\n",
        encoding="utf-8",
    )
    (root / ".cursor/session/CURRENT_CHAT.md").write_text(
        "chat_id: chat_test_001\n",
        encoding="utf-8",
    )
    (root / ".cursor/session/chats/chat_test_001.md").write_text(
        "# Chat\n\nGoal: test memory\n",
        encoding="utf-8",
    )
    (root / ".cursor/session/OPEN_CHATS.yaml").write_text(
        "open:\n"
        "- id: chat_test_001\n"
        "  goal: test memory\n"
        "  open_questions: []\n"
        "  files_touched: []\n"
        "  status: active\n",
        encoding="utf-8",
    )


def test_append_decision_goes_to_decisions_section(tmp_path):
    """Test append decision goes to decisions section. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    _minimal_setup(root)
    append_decision(root, "Use pytest for all behaviour changes")
    text = (root / ".cursor/session/REPO_SESSION.md").read_text(encoding="utf-8")
    assert "Use pytest" in text
    dec_start = text.index("## Decisions")
    act_start = text.index("## Activity")
    assert dec_start < act_start
    assert "Use pytest" in text[dec_start:act_start]


def test_log_decision_flag(tmp_path):
    """Test log decision flag. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    _minimal_setup(root)
    console = HyperConsole(plain=True)
    run_log(root, console, decision="Always run doctor --tier ready after setup")
    text = (root / ".cursor/session/REPO_SESSION.md").read_text(encoding="utf-8")
    assert "doctor --tier ready" in text


def test_log_resolve_question(tmp_path):
    """Test log resolve question. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    _minimal_setup(root)
    (root / ".cursor/session/OPEN_CHATS.yaml").write_text(
        "open:\n"
        "- id: chat_test_001\n"
        "  goal: test\n"
        "  open_questions:\n"
        "  - Which auth provider?\n"
        "  files_touched: []\n"
        "  status: active\n",
        encoding="utf-8",
    )
    console = HyperConsole(plain=True)
    run_log(root, console, resolve_question="Which auth provider?")
    from hypercharge.session import get_open_chat_entry

    entry = get_open_chat_entry(root, "chat_test_001")
    assert entry.get("open_questions") == []


def test_context_packet_includes_goal(tmp_path):
    """Test context packet includes goal. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    _minimal_setup(root)
    packet = build_context_packet(root, budget=500)
    assert "test memory" in packet
    assert "context packet" in packet.lower()


def test_log_defer_question_archives(tmp_path):
    """Test log defer question archives. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    _minimal_setup(root)
    (root / ".cursor/session/OPEN_CHATS.yaml").write_text(
        "open:\n"
        "- id: chat_test_001\n"
        "  goal: test\n"
        "  open_questions:\n"
        "  - Which auth provider?\n"
        "  files_touched: []\n"
        "  status: active\n",
        encoding="utf-8",
    )
    console = HyperConsole(plain=True)
    run_log(root, console, defer_question="Which auth provider?")
    deferred = root / ".cursor/session/DEFERRED_QUESTIONS.md"
    assert deferred.is_file()
    assert "Which auth provider?" in deferred.read_text(encoding="utf-8")


def test_context_packet_includes_chat_tail(tmp_path):
    """Test context packet includes chat tail. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    _minimal_setup(root)
    chat = root / ".cursor/session/chats/chat_test_001.md"
    chat.write_text("# Chat\n\nGoal: test memory\n\n- did important work\n", encoding="utf-8")
    packet = build_context_packet(root, budget=500)
    assert "did important work" in packet


def test_long_query_includes_phrase_match():
    """Queries with >1 token should produce a FTS5 quoted-phrase term."""
    from hypercharge.memory_index import _build_fts_query

    long_query = "auth session state machine rate limiting retry strategy"
    fts_q = _build_fts_query(long_query)

    assert f'"{long_query}"' in fts_q
    assert '"session"' in fts_q
    assert "session*" in fts_q


def test_archive_ttl_skips_old_files(tmp_path):
    """Archive files older than 90 days must not be ingested during rebuild."""
    import os
    import time

    from hypercharge.memory_index import rebuild_memory_index, search_memory_index

    root = tmp_path / "repo"
    root.mkdir()
    _minimal_setup(root)

    archive = root / ".cursor/session/archive"
    archive.mkdir(parents=True)

    recent = archive / "recent.md"
    recent.write_text("# Recent\nrecent unique xqzjw content here", encoding="utf-8")

    old = archive / "old.md"
    old.write_text("# Old\nold unique xqzjw content here", encoding="utf-8")

    old_mtime = time.time() - (91 * 86400)
    os.utime(old, (old_mtime, old_mtime))

    rebuild_memory_index(root)

    recent_hits = search_memory_index(root, "recent unique xqzjw", limit=10)
    old_hits = search_memory_index(root, "old unique xqzjw", limit=10)

    assert any("recent.md" in r["path"] for r in recent_hits)
    assert not any("old.md" in r["path"] for r in old_hits)
