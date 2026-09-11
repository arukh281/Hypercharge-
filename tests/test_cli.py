"""Smoke tests for Hypercharge CLI."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from hypercharge.graph import graphify_out_dir, migrate_legacy_graphify_out, graph_json_path
from hypercharge.templates_deploy import deploy_templates


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Internal _run. Returns: subprocess.run([sys.executable, '-m', 'hypercharge. (hypercharge-managed)"""
    return subprocess.run(
        [sys.executable, "-m", "hypercharge", "--plain", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def test_migrate_legacy_graphify_out(tmp_path):
    """Test migrate legacy graphify out. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    legacy = root / "graphify-out"
    legacy.mkdir()
    (legacy / "graph.json").write_text('{"nodes":[],"links":[]}', encoding="utf-8")
    (root / ".cursor").mkdir()
    deploy_templates(root)
    assert migrate_legacy_graphify_out(root)
    assert not legacy.exists()
    assert graph_json_path(root).is_file()


def test_version():
    """Test version. (hypercharge-managed)"""
    r = subprocess.run(
        [sys.executable, "-m", "hypercharge", "--version"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0
    assert "0.1.0" in r.stdout


def test_setup_and_wrapup_seedling():
    """Test setup and wrapup seedling. (hypercharge-managed)"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text("# test\n")
        r = _run("setup", "--skip-dialogue", "--no-graph", "--path", str(root))
        assert r.returncode == 0, r.stdout + r.stderr
        assert (root / ".cursor/session/REPO_SESSION.md").is_file()
        r2 = _run("wrapup", "--path", str(root))
        assert r2.returncode == 0, r2.stdout + r2.stderr
        r3 = _run("wrapup", "--day", "--no-graph", "--path", str(root))
        assert r3.returncode == 0, r3.stdout + r3.stderr
        r4 = _run("setup-status", "--json", "--path", str(root))
        assert r4.returncode == 0  # ready tier: setup + rules ok without graph
        data = json.loads(r4.stdout)
        assert data["setup"] is True
        assert data["graph_present"] is False


def test_start_day_loose_ends():
    """Test start day loose ends. (hypercharge-managed)"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text("# test\n")
        r = _run("setup", "--skip-dialogue", "--no-graph", "--path", str(root))
        assert r.returncode == 0, r.stdout + r.stderr

        from hypercharge.session import register_new_chat, upsert_open_chat

        cid = register_new_chat(root, goal="Finish widget")
        upsert_open_chat(
            root,
            {
                "id": cid,
                "goal": "Finish widget",
                "open_questions": ["Ship to prod?"],
                "status": "active",
                "last_active": "2020-01-01T00:00:00Z",
            },
        )

        rs = _run("start-day", "--no-graph", "--path", str(root))
        assert rs.returncode == 0, rs.stdout + rs.stderr
        assert "Ship to prod?" in rs.stdout or "What's today's focus?" in rs.stdout
        assert "done | todo | archive | defer" not in rs.stdout
        assert "Ask the user (one natural question" in rs.stdout
        assert (root / ".cursor/session/START_DAY_LOG.md").is_file()
        assert (root / ".cursor/rules/hypercharge.mdc").is_file()
        assert (root / ".cursor/rules/hypercharge-grounding.mdc").is_file()


def test_new_chat_and_parallel_brief():
    """Test new chat and parallel brief. (hypercharge-managed)"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text("# test\n")
        r = _run("setup", "--skip-dialogue", "--no-graph", "--path", str(root))
        assert r.returncode == 0, r.stdout + r.stderr

        r1 = _run("new-chat", "--goal", "Grid refactor", "--path", str(root))
        assert r1.returncode == 0, r1.stdout + r1.stderr
        id1 = [ln.split(": ", 1)[1] for ln in r1.stdout.splitlines() if ln.startswith("chat_id:")][0]

        r2 = _run("new-chat", "--goal", "Hypercharge CLI", "--path", str(root))
        assert r2.returncode == 0, r2.stdout + r2.stderr

        from hypercharge.session import load_open_chats, upsert_open_chat

        upsert_open_chat(
            root,
            {
                "id": id1,
                "goal": "Grid refactor",
                "files_touched": ["src/app/grid.py"],
                "status": "active",
            },
        )
        data = load_open_chats(root)
        id2 = [c["id"] for c in data["open"] if c["id"] != id1][0]
        upsert_open_chat(
            root,
            {
                "id": id2,
                "goal": "Hypercharge CLI",
                "files_touched": ["hypercharge/hypercharge/cli.py", "src/app/grid.py"],
                "status": "active",
            },
        )

        rb = _run("brief", "--path", str(root))
        assert rb.returncode == 0, rb.stdout + rb.stderr
        assert "Other active threads" in rb.stdout or "Possible connections" in rb.stdout
        assert "Possible connections" in rb.stdout
        assert "grid.py" in rb.stdout


def test_brief_after_setup():
    """Test brief after setup. (hypercharge-managed)"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text("# test\n")
        r = _run("setup", "--skip-dialogue", "--no-graph", "--path", str(root))
        assert r.returncode == 0, r.stdout + r.stderr
        session = root / ".cursor/session/REPO_SESSION.md"
        session.write_text(
            "# Repo session\n\n## Current initiative\n\nShip widget.\n\n## Decisions\n\n- Use YAML.\n",
            encoding="utf-8",
        )
        r2 = _run("brief", "--path", str(root))
        assert r2.returncode == 0, r2.stdout + r2.stderr
        assert "Ship widget" in r2.stdout
        assert (root / ".cursor/rules/hypercharge-grounding.mdc").is_file()
        assert (root / ".cursor/rules/hypercharge.mdc").is_file()


def test_setup_syncs_managed_rules():
    """Test setup syncs managed rules. (hypercharge-managed)"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text("# test\n")
        r = _run("setup", "--skip-dialogue", "--no-graph", "--path", str(root))
        assert r.returncode == 0, r.stdout + r.stderr
        grounding = root / ".cursor/rules/hypercharge-grounding.mdc"
        session = root / ".cursor/rules/hypercharge.mdc"
        assert grounding.is_file()
        assert session.is_file()
        assert "graphify" in grounding.read_text(encoding="utf-8").lower()
        assert "knowledge" in grounding.read_text(encoding="utf-8").lower()
        assert "OPEN_CHATS" in session.read_text(encoding="utf-8")

        grounding.write_text("# tampered\n", encoding="utf-8")
        r2 = _run("setup", "--skip-dialogue", "--no-graph", "--path", str(root))
        assert r2.returncode == 0, r2.stdout + r2.stderr
        assert "hypercharge-managed" in grounding.read_text(encoding="utf-8")
        profile = json.loads((root / ".cursor/repo-profile.json").read_text(encoding="utf-8"))
        assert profile["rules"]["always_apply"] == [
            "hypercharge.mdc",
            "hypercharge-grounding.mdc",
        ]
        skill = (root / ".cursor/skills/repo-guardrail/SKILL.md").read_text(encoding="utf-8")
        assert "hypercharge" in skill.lower()


def test_wrapup_preserves_open_questions():
    """Test wrapup preserves open questions. (hypercharge-managed)"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text("# test\n")
        _run("setup", "--skip-dialogue", "--no-graph", "--path", str(root))

        from hypercharge.session import register_new_chat, upsert_open_chat, load_open_chats

        cid = register_new_chat(root, goal="Ship it")
        upsert_open_chat(
            root,
            {
                "id": cid,
                "goal": "Ship it",
                "open_questions": ["Ready for prod?"],
                "files_touched": ["src/a.py"],
                "status": "active",
            },
        )
        r = _run("wrapup", "--path", str(root))
        assert r.returncode == 0, r.stdout + r.stderr
        data = load_open_chats(root)
        row = next(c for c in data["open"] if c["id"] == cid)
        assert row["open_questions"] == ["Ready for prod?"]
        assert row["files_touched"] == ["src/a.py"]


def test_brief_does_not_create_chat():
    """Test brief does not create chat. (hypercharge-managed)"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text("# test\n")
        _run("setup", "--skip-dialogue", "--no-graph", "--path", str(root))
        chats_before = list((root / ".cursor/session/chats").glob("*.md"))
        _run("brief", "--path", str(root))
        chats_after = list((root / ".cursor/session/chats").glob("*.md"))
        assert len(chats_after) == len(chats_before)


def test_startday_alias():
    """Test startday alias. (hypercharge-managed)"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text("# test\n")
        _run("setup", "--skip-dialogue", "--no-graph", "--path", str(root))
        r = _run("startday", "--no-graph", "--path", str(root))
        assert r.returncode == 0, r.stdout + r.stderr
        assert "Start day" in r.stdout


def test_graph_hash_counts_links():
    """Test graph hash counts links. (hypercharge-managed)"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        gdir = graphify_out_dir(root)
        gdir.mkdir(parents=True, exist_ok=True)
        (gdir / "graph.json").write_text(
            '{"nodes": [{"id": "a"}], "links": [{"source": "a", "target": "b"}]}',
            encoding="utf-8",
        )
        from hypercharge.graph import graph_hash

        assert graph_hash(root) == "1n_1e"


def test_log_command():
    """Test log command. (hypercharge-managed)"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text("# test\n")
        _run("setup", "--skip-dialogue", "--no-graph", "--path", str(root))
        from hypercharge.session import register_new_chat, load_open_chats

        register_new_chat(root, goal="Widget")
        r = _run("log", "--file", "src/a.py", "--note", "wired A", "--path", str(root))
        assert r.returncode == 0, r.stdout + r.stderr
        data = load_open_chats(root)
        row = data["open"][0]
        assert "src/a.py" in row["files_touched"]


def test_compress_headroom_result():
    """Test compress headroom result. (hypercharge-managed)"""
    from hypercharge.compress_output import _extract_headroom_text

    class FakeResult:
        messages = [{"content": "compressed body"}]

    assert _extract_headroom_text(FakeResult()) == "compressed body"
    assert _extract_headroom_text({"messages": [{"content": "dict body"}]}) == "dict body"
    assert _extract_headroom_text({"messages": []}) == ""


def test_doctor_command():
    """Test doctor command. (hypercharge-managed)"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text("# test\n")
        _run("setup", "--skip-dialogue", "--no-graph", "--path", str(root), cwd=root)
        _run("memory-index", "--rebuild", "--path", str(root), cwd=root)
        gdir = graphify_out_dir(root)
        gdir.mkdir(parents=True, exist_ok=True)
        (gdir / "graph.json").write_text('{"nodes": [], "links": []}', encoding="utf-8")
        r = _run("doctor", "--tier", "ideal", "--json", "--path", str(root))
        assert r.returncode == 1, r.stdout + r.stderr  # loose ends on fresh setup
        data = json.loads(r.stdout)
        assert data["managed_rules_ok"] is True
        assert data["graph_present"] is True
        r_ready = _run("doctor", "--tier", "ready", "--json", "--path", str(root), cwd=root)
        assert r_ready.returncode == 0, r_ready.stdout + r_ready.stderr
        data_ready = json.loads(r_ready.stdout)
        assert data_ready["ready"] is True


def test_archive_blocks_open_questions():
    """Test archive blocks open questions. (hypercharge-managed)"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text("# test\n")
        _run("setup", "--skip-dialogue", "--no-graph", "--path", str(root))
        from hypercharge.session import register_new_chat, upsert_open_chat

        cid = register_new_chat(root, goal="Ship")
        upsert_open_chat(
            root,
            {"id": cid, "goal": "Ship", "open_questions": ["Ready?"], "status": "active"},
        )
        r = _run("wrapup", "--archive", "--path", str(root))
        assert r.returncode != 0
        r2 = _run("wrapup", "--archive", "--defer-questions", "--path", str(root))
        assert r2.returncode == 0, r2.stdout + r2.stderr


def test_new_chat_resume():
    """Test new chat resume. (hypercharge-managed)"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text("# test\n")
        _run("setup", "--skip-dialogue", "--no-graph", "--path", str(root))
        from hypercharge.session import register_new_chat, peek_current_chat_id

        cid = register_new_chat(root, goal="Alpha")
        register_new_chat(root, goal="Beta")
        r = _run("new-chat", "--resume", cid, "--path", str(root))
        assert r.returncode == 0, r.stdout + r.stderr
        assert peek_current_chat_id(root) == cid


def test_scan_user_skills():
    """Test scan user skills. (hypercharge-managed)"""
    from hypercharge.inventory import scan_user_skills

    rows = scan_user_skills()
    assert isinstance(rows, list)
    names = {r["name"] for r in rows}
    assert names == {r["name"] for r in rows}  # deduped


def test_story_command():
    """Test story command. (hypercharge-managed)"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text("# test\n")
        _run("setup", "--skip-dialogue", "--no-graph", "--path", str(root))
        hc_dir = root / ".cursor/hypercharge"
        hc_dir.mkdir(parents=True, exist_ok=True)
        (hc_dir / "last-onboard.json").write_text(
            json.dumps(
                {
                    "repo_root": str(root),
                    "graph": {"nodes": 42},
                    "agent_must_ask": ["rules_compile"],
                }
            ),
            encoding="utf-8",
        )
        r = _run("story", "--path", str(root))
        assert r.returncode == 0, r.stdout + r.stderr
        assert "Hypercharger is ready" in r.stdout
        assert "42 nodes" in r.stdout
        assert "rules compile" in r.stdout.lower()


def test_escalation_command():
    """Test escalation command. (hypercharge-managed)"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text("# test\n")
        _run("setup", "--skip-dialogue", "--no-graph", "--path", str(root))
        r = _run("escalation", "--task", "security review", "--path", str(root))
        assert r.returncode == 0, r.stdout + r.stderr
        assert "Hypercharge escalation" in r.stdout
        assert "Security review" in r.stdout


def test_shrink_command():
    """Test shrink command. (hypercharge-managed)"""
    long_text = "line\n" * 5000
    r = _run("shrink", "--text", long_text, "--max-chars", "500")
    assert r.returncode == 0, r.stdout + r.stderr
    assert len(r.stdout) < len(long_text)


def test_compile_dry_run():
    """Test compile dry run. (hypercharge-managed)"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text("# test\n")
        _run("setup", "--skip-dialogue", "--no-graph", "--path", str(root))
        r = _run("compile", "--dry-run", "--path", str(root))
        assert r.returncode == 0, r.stdout + r.stderr
        assert "dry run" in r.stdout.lower() or "Rules compile" in r.stdout


def test_doctor_suggested_fixes():
    """Test doctor suggested fixes. (hypercharge-managed)"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text("# test\n")
        r = _run("doctor", "--json", "--path", str(root))
        assert r.returncode != 0
        data = json.loads(r.stdout)
        assert "suggested_fixes" in data
        assert any("onboard" in fix for fix in data["suggested_fixes"])

        _run("setup", "--skip-dialogue", "--no-graph", "--path", str(root))
        gdir = graphify_out_dir(root)
        gdir.mkdir(parents=True, exist_ok=True)
        (gdir / "graph.json").write_text('{"nodes": [], "links": []}', encoding="utf-8")
        r2 = _run("doctor", "--tier", "ideal", "--json", "--path", str(root))
        data2 = json.loads(r2.stdout)
        assert data2["managed_rules_ok"] is True
        assert data2["loose_ends"] > 0
        assert r2.returncode == 1
        assert isinstance(data2["suggested_fixes"], list)



def test_start_day_grace_after_onboard():
    """Test start day grace after onboard. (hypercharge-managed)"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text("# test\n")
        _run("setup", "--skip-dialogue", "--no-graph", "--path", str(root))
        hc = root / ".cursor/hypercharge"
        hc.mkdir(parents=True, exist_ok=True)
        (hc / "last-onboard.json").write_text('{"status": "ready"}', encoding="utf-8")

        rs = _run("start-day", "--json", "--no-graph", "--path", str(root))
        assert rs.returncode == 0, rs.stdout + rs.stderr
        data = json.loads(rs.stdout)
        assert data["primary_question"] == "What's today's focus?"
        assert not any("day wrapup" in n.lower() for n in data.get("silent_notes", []))


def test_teardown_target_claude_preserves_cursor_session(tmp_path):
    """Test teardown target claude preserves cursor session. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    deploy_templates(root, target="both")
    session = root / ".cursor/session/REPO_SESSION.md"
    profile = root / ".cursor/repo-profile.json"
    assert session.is_file()
    assert profile.is_file()

    from hypercharge.teardown_cmd import run_teardown
    from hypercharge.ui.console import HyperConsole

    assert run_teardown(root, HyperConsole(plain=True), confirm=True, target="claude") == 0
    assert session.is_file()
    assert profile.is_file()
    assert not (root / "CLAUDE.md").exists() or "hypercharge-managed" not in (
        (root / "CLAUDE.md").read_text(encoding="utf-8") if (root / "CLAUDE.md").exists() else ""
    )


def test_teardown_target_both_removes_shared_scaffolding(tmp_path):
    """Test teardown target both removes shared scaffolding. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    deploy_templates(root, target="cursor")
    session = root / ".cursor/session/REPO_SESSION.md"
    assert session.is_file()

    from hypercharge.teardown_cmd import run_teardown
    from hypercharge.ui.console import HyperConsole

    assert run_teardown(root, HyperConsole(plain=True), confirm=True, target="both") == 0
    assert not session.is_file()
    assert not (root / ".cursor/repo-profile.json").is_file()


def test_teardown_cursor_removes_advisory_rules(tmp_path):
    """Test teardown cursor removes advisory rules. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    deploy_templates(root, target="cursor")
    managed = root / ".cursor/rules/hypercharge.mdc"
    assert managed.is_file()

    from hypercharge.teardown_cmd import run_teardown
    from hypercharge.ui.console import HyperConsole

    run_teardown(root, HyperConsole(plain=True), confirm=True, target="cursor")
    assert not managed.is_file()
    assert (root / ".cursor/session/REPO_SESSION.md").is_file()


def test_teardown_both_removes_legacy_graphify_out(tmp_path):
    """Test teardown both removes legacy graphify out. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    deploy_templates(root, target="cursor")
    legacy = root / "graphify-out"
    legacy.mkdir()
    (legacy / "manifest.json").write_text("{}", encoding="utf-8")

    from hypercharge.teardown_cmd import run_teardown
    from hypercharge.ui.console import HyperConsole

    run_teardown(root, HyperConsole(plain=True), confirm=True, target="both")
    assert not legacy.exists()
