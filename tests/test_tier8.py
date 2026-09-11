"""Tier 8 — shell grounding gate + semantic memory index."""

from __future__ import annotations

import json

import pytest
from pathlib import Path
from unittest.mock import patch

from hypercharge.grounding_session import is_path_grounded, record_query_success
from hypercharge.hook_handlers import handle_pre_tool_use
from hypercharge.memory_index import rebuild_memory_index, search_memory_index
from hypercharge.shell_gate import assess_shell_command
from hypercharge.templates_deploy import deploy_templates
from hypercharge.ui.console import HyperConsole


def test_shell_safe_hypercharge():
    """Test shell safe hypercharge. (hypercharge-managed)"""
    a = assess_shell_command("hypercharge knowledge 'auth flow'")
    assert a.safe
    assert not a.needs_grounding


def test_shell_extracts_cat_path():
    """cat is allowlisted safe — assess_shell_command reports safe=True, no paths extracted."""
    a = assess_shell_command("cat hypercharge/auth.py")
    assert a.safe
    assert a.reason == "allowlisted"


def test_shell_allows_cat_always(tmp_path):
    """cat is in the safe-prefix allowlist — always allow regardless of grounding."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "hypercharge").mkdir()
    (root / "hypercharge/auth.py").write_text("# auth\n", encoding="utf-8")
    (root / ".cursor/hypercharge").mkdir(parents=True)
    result = handle_pre_tool_use(
        root,
        {"tool_name": "Shell", "tool_input": {"command": "cat hypercharge/auth.py"}},
    )
    assert result.get("permission") == "allow"


def test_shell_allows_grounded_cat(tmp_path):
    """Test shell allows grounded cat. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "hypercharge").mkdir()
    (root / "hypercharge/auth.py").write_text("# auth\n", encoding="utf-8")
    (root / ".cursor/hypercharge").mkdir(parents=True)
    record_query_success(root, ["hypercharge/auth.py"])
    result = handle_pre_tool_use(
        root,
        {"tool_name": "Shell", "tool_input": {"command": "cat hypercharge/auth.py"}},
    )
    assert result.get("permission") == "allow"
    assert is_path_grounded(root, "hypercharge/auth.py")


def test_shell_allows_pytest():
    """Test shell allows pytest. (hypercharge-managed)"""
    result = assess_shell_command(".venv/bin/python -m pytest tests/ -q")
    assert result.safe


def test_shell_warns_sed_inplace(tmp_path):
    """Warn policy: sed -i on ungrounded path warns (allow + agent_message), does not deny."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src/foo.py").write_text("# foo\n", encoding="utf-8")
    (root / ".cursor/hypercharge").mkdir(parents=True)
    result = handle_pre_tool_use(
        root,
        {"tool_name": "shell", "tool_input": {"command": "sed -i '' 's/a/b/' src/foo.py"}},
    )
    assert result.get("permission") == "allow"
    assert result.get("agent_message")


def test_memory_index_rebuild_and_search(tmp_path):
    """Test memory index rebuild and search. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".cursor/session").mkdir(parents=True)
    (root / ".cursor/session/REPO_SESSION.md").write_text(
        "# Repo session\n\n## Decisions\n\nUse JWT middleware for authentication tokens.\n",
        encoding="utf-8",
    )
    count = rebuild_memory_index(root)
    assert count >= 1
    hits = search_memory_index(root, "authentication middleware", limit=3)
    assert hits
    assert any("JWT" in h["excerpt"] or "authentication" in h["excerpt"].lower() for h in hits)


def test_shell_allows_safe_command_regardless_of_policy(tmp_path):
    """cat is allowlisted as a safe command — always allow, no agent_message."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "Makefile").write_text("all:\n", encoding="utf-8")
    (root / ".cursor/hypercharge").mkdir(parents=True)
    result = handle_pre_tool_use(
        root,
        {"tool_name": "Shell", "tool_input": {"command": "cat Makefile"}},
    )
    assert result.get("permission") == "allow"


def test_shell_allows_safe_compound(tmp_path):
    """pytest && cat are both safe-prefixed — compound of two safe commands is allowed."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "hypercharge").mkdir()
    (root / "hypercharge/secret.py").write_text("# s\n", encoding="utf-8")
    (root / ".cursor/hypercharge").mkdir(parents=True)
    result = handle_pre_tool_use(
        root,
        {"tool_name": "run_terminal_cmd", "tool_input": {"command": "pytest tests/ -q && cat hypercharge/secret.py"}},
    )
    assert result.get("permission") == "allow"


def test_shell_advises_on_unparsed_command(tmp_path):
    """Unparsed shell command (e.g. vim) is always allowed — context enrichment only."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".cursor/hypercharge").mkdir(parents=True)
    result = handle_pre_tool_use(
        root,
        {"tool_name": "Shell", "tool_input": {"command": "vim"}},
    )
    assert result.get("permission") == "allow"


def test_log_appends_memory_chunk(tmp_path):
    """Test log appends memory chunk. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".cursor/session/chats").mkdir(parents=True)
    (root / ".cursor/session/CURRENT_CHAT.md").write_text("chat_id: c1\n", encoding="utf-8")
    (root / ".cursor/session/chats/c1.md").write_text("# chat\n", encoding="utf-8")
    (root / ".cursor/session/OPEN_CHATS.yaml").write_text(
        "open:\n- id: c1\n  goal: test\n  open_questions: []\n  files_touched: []\n  status: active\n",
        encoding="utf-8",
    )
    from hypercharge.log_cmd import run_log
    from hypercharge.ui.console import HyperConsole

    run_log(root, HyperConsole(plain=True), decision="Always index decisions in memory FTS")
    hits = search_memory_index(root, "index decisions memory", limit=3)
    assert hits
    assert any("index decisions" in h["excerpt"].lower() or "Always" in h["excerpt"] for h in hits)


def test_knowledge_includes_memory_index(tmp_path):
    """Test knowledge includes memory index. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".cursor/session").mkdir(parents=True)
    (root / ".cursor/session/REPO_SESSION.md").write_text(
        "# Repo session\n\n## Decisions\n\nPrefer sqlite FTS for semantic memory recall.\n",
        encoding="utf-8",
    )
    rebuild_memory_index(root)
    from hypercharge.knowledge_cmd import _session_knowledge

    body = _session_knowledge(root, "semantic memory recall")
    assert "## MEMORY index" in body
    assert "MEMORY" in body


def test_context_packet_includes_memory_recall(tmp_path):
    """Test context packet includes memory recall. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".cursor/session").mkdir(parents=True)
    (root / ".cursor/session/chats").mkdir(parents=True)
    (root / ".cursor/session/CURRENT_CHAT.md").write_text("chat_id: c1\n", encoding="utf-8")
    (root / ".cursor/session/chats/c1.md").write_text("Goal: ship memory recall\n", encoding="utf-8")
    (root / ".cursor/session/OPEN_CHATS.yaml").write_text(
        "open:\n- id: c1\n  goal: ship memory recall\n  open_questions: []\n  files_touched: []\n  status: active\n",
        encoding="utf-8",
    )
    (root / ".cursor/session/REPO_SESSION.md").write_text(
        "# Repo session\n\n## Decisions\n\nUse FTS memory for recall.\n",
        encoding="utf-8",
    )
    rebuild_memory_index(root)
    from hypercharge.context_packet_cmd import build_context_packet

    packet = build_context_packet(root, budget=800)
    assert "MEMORY recall" in packet or "FTS memory" in packet


def test_wrapup_rebuilds_memory_index(tmp_path):
    """Test wrapup rebuilds memory index. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("# test\n", encoding="utf-8")
    (root / ".cursor/session/chats").mkdir(parents=True)
    (root / ".cursor/hypercharge").mkdir(parents=True)
    (root / ".cursor/session/CURRENT_CHAT.md").write_text("chat_id: c1\n", encoding="utf-8")
    (root / ".cursor/session/chats/c1.md").write_text("# chat\n", encoding="utf-8")
    (root / ".cursor/session/OPEN_CHATS.yaml").write_text(
        "open:\n- id: c1\n  goal: test\n  open_questions: []\n  files_touched: []\n  status: active\n",
        encoding="utf-8",
    )
    (root / ".cursor/session/REPO_SESSION.md").write_text(
        "# Repo session\n\n## Decisions\n\nRebuild memory on wrapup day.\n",
        encoding="utf-8",
    )
    from hypercharge.wrapup_cmd import run_wrapup
    from hypercharge.ui.console import HyperConsole
    from hypercharge.memory_index import index_path

    run_wrapup(root, HyperConsole(plain=True), day=True, no_graph=True)
    assert index_path(root).is_file()
    hits = search_memory_index(root, "wrapup memory rebuild", limit=3)
    assert hits


def test_normalize_repo_path_absolute(tmp_path):
    """Test normalize repo path absolute. Args: tmp_path. (hypercharge-managed)"""
    from hypercharge.grounding_session import normalize_repo_path

    root = tmp_path / "repo"
    root.mkdir()
    (root / "hypercharge").mkdir()
    (root / "hypercharge/foo.py").write_text("# x\n", encoding="utf-8")
    abs_path = (root / "hypercharge/foo.py").resolve()
    assert normalize_repo_path(root, str(abs_path)) == "hypercharge/foo.py"


def test_sibling_not_over_grounded(tmp_path):
    """Test sibling not over grounded. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".cursor/hypercharge").mkdir(parents=True)
    (root / "hypercharge").mkdir()
    (root / "hypercharge/auth.py").write_text("# a\n", encoding="utf-8")
    (root / "hypercharge/secret.py").write_text("# s\n", encoding="utf-8")
    record_query_success(root, ["hypercharge/auth.py"])
    assert is_path_grounded(root, "hypercharge/auth.py")
    assert not is_path_grounded(root, "hypercharge/secret.py")


def test_shell_allows_git_show(tmp_path):
    """git show is allowlisted — always allow regardless of grounding."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".cursor/hypercharge").mkdir(parents=True)
    (root / "hypercharge").mkdir()
    (root / "hypercharge/auth.py").write_text("# a\n", encoding="utf-8")
    a = assess_shell_command("git show HEAD:hypercharge/auth.py")
    assert a.safe
    result = handle_pre_tool_use(
        root,
        {"tool_name": "Shell", "tool_input": {"command": "git show HEAD:hypercharge/auth.py"}},
    )
    assert result.get("permission") == "allow"


def test_shell_allows_ls_path(tmp_path):
    """ls is allowlisted — always allow regardless of grounding."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".cursor/hypercharge").mkdir(parents=True)
    (root / "hypercharge").mkdir()
    result = handle_pre_tool_use(
        root,
        {"tool_name": "Shell", "tool_input": {"command": "ls hypercharge/"}},
    )
    assert result.get("permission") == "allow"


def test_delete_and_mcp_warn(tmp_path):
    """Warn policy: Delete/CallMcpTool warn (allow + agent_message); Task passes through."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".cursor/hypercharge").mkdir(parents=True)
    (root / "src").mkdir()
    (root / "src/foo.py").write_text("# x\n", encoding="utf-8")
    delete_result = handle_pre_tool_use(
        root, {"tool_name": "Delete", "tool_input": {"path": "src/foo.py"}}
    )
    assert delete_result.get("permission") == "allow"
    assert delete_result.get("agent_message")
    assert handle_pre_tool_use(
        root, {"tool_name": "Task", "tool_input": {"prompt": "explore"}}
    ).get("permission") == "allow"


def test_sapling_advises_on_curl(tmp_path):
    """Network commands always produce allow + HEADS UP advisory — never blocked."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".cursor/hypercharge").mkdir(parents=True)
    result = handle_pre_tool_use(
        root, {"tool_name": "Shell", "tool_input": {"command": "curl https://example.com"}}
    )
    assert result.get("permission") == "allow"
    assert result.get("agent_message")
    assert "network" in result["agent_message"].lower() or "HEADS UP" in result["agent_message"]


def test_pathless_semantic_search_allowed_in_warn(tmp_path):
    """Warn policy: pathless SemanticSearch passes through (no block)."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".cursor/hypercharge").mkdir(parents=True)
    result = handle_pre_tool_use(
        root,
        {"tool_name": "SemanticSearch", "tool_input": {"query": "auth flow"}},
    )
    assert result.get("permission") == "allow"


def test_log_decision_redacts_incremental_index(tmp_path):
    """Test log decision redacts incremental index. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".cursor/session/chats").mkdir(parents=True)
    (root / ".cursor/session/CURRENT_CHAT.md").write_text("chat_id: c1\n", encoding="utf-8")
    (root / ".cursor/session/chats/c1.md").write_text("# chat\n", encoding="utf-8")
    (root / ".cursor/session/OPEN_CHATS.yaml").write_text(
        "open:\n- id: c1\n  goal: test\n  open_questions: []\n  files_touched: []\n  status: active\n",
        encoding="utf-8",
    )
    from hypercharge.log_cmd import run_log

    run_log(root, HyperConsole(plain=True), decision="Store api_key=leaked_secret_here")
    hits = search_memory_index(root, "leaked_secret", limit=3)
    assert not hits
    hits2 = search_memory_index(root, "REDACTED", limit=3)
    assert hits2
    assert "leaked_secret_here" not in hits2[0]["excerpt"]


def test_wrapup_chat_rebuilds_memory(tmp_path):
    """Test wrapup chat rebuilds memory. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".cursor/hypercharge").mkdir(parents=True)
    (root / ".cursor/session/chats").mkdir(parents=True)
    (root / ".cursor/session/CURRENT_CHAT.md").write_text("chat_id: c1\n", encoding="utf-8")
    (root / ".cursor/session/chats/c1.md").write_text("# chat\n", encoding="utf-8")
    (root / ".cursor/session/OPEN_CHATS.yaml").write_text(
        "open:\n- id: c1\n  goal: test\n  open_questions: []\n  files_touched: []\n  status: active\n",
        encoding="utf-8",
    )
    (root / ".cursor/session/REPO_SESSION.md").write_text(
        "# Repo session\n\n## Decisions\n\nRebuild on chat wrapup.\n",
        encoding="utf-8",
    )
    from hypercharge.memory_index import index_path
    from hypercharge.ui.console import HyperConsole
    from hypercharge.wrapup_cmd import run_wrapup

    run_wrapup(root, HyperConsole(plain=True), no_graph=True)
    assert index_path(root).is_file()


def test_memory_redacts_secrets(tmp_path):
    """Test memory redacts secrets. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".cursor/session").mkdir(parents=True)
    (root / ".cursor/session/REPO_SESSION.md").write_text(
        "# Repo session\n\n## Decisions\n\napi_key=supersecret123\n",
        encoding="utf-8",
    )
    rebuild_memory_index(root)
    hits = search_memory_index(root, "Decisions", limit=3)
    assert hits
    assert "supersecret123" not in hits[0]["excerpt"]
    assert "[REDACTED]" in hits[0]["excerpt"]


def test_shell_advises_on_curl_and_subshell(tmp_path):
    """Network/subshell commands always allow with HEADS UP advisory — never blocked."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".cursor/hypercharge").mkdir(parents=True)
    for cmd in ("curl https://example.com", "$(cat hypercharge/secret.py)"):
        result = handle_pre_tool_use(
            root, {"tool_name": "Shell", "tool_input": {"command": cmd}}
        )
        assert result.get("permission") == "allow"
        assert result.get("agent_message")


def test_golden_path_lifecycle(tmp_path):
    """Test golden path lifecycle. Args: tmp_path. Returns: sp.CompletedProcess(args=[], returncode=0, stdout=. (hypercharge-managed)"""
    import subprocess
    from unittest.mock import patch

    from hypercharge.context import run_grounded_query
    from hypercharge.doctor_cmd import build_doctor_report, _doctor_exit_code
    from hypercharge.graph import graphify_out_dir
    from hypercharge.onboard_cmd import run_onboard
    from hypercharge.wrapup_cmd import run_wrapup

    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("# demo\n", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src/auth.py").write_text("# auth\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    assert (
        run_onboard(
            root,
            HyperConsole(plain=True),
            skip_machine_install=True,
            no_graph=True,
            as_json=True,
        )
        == 0
    )
    gdir = graphify_out_dir(root)
    gdir.mkdir(parents=True, exist_ok=True)
    (gdir / "graph.json").write_text(
        json.dumps(
            {"nodes": [{"source_file": "src/auth.py", "community": 0}], "links": []}
        ),
        encoding="utf-8",
    )

    def sparse_query(*_a, **_k):
        """Sparse query. Returns: sp.CompletedProcess(args=[], returncode=0, stdout=. (hypercharge-managed)"""
        import subprocess as sp

        return sp.CompletedProcess(args=[], returncode=0, stdout="sparse module map only\n", stderr="")

    with (
        patch("hypercharge.context.ensure_context_ready", return_value=True),
        patch("hypercharge.context.graph_is_present", return_value=True),
        patch("hypercharge.context._run_graphify_query", sparse_query),
    ):
        code, _ = run_grounded_query(root, "auth module src")
    assert code == 1  # sparse graphify → no real citations → honest exit 1
    # Simulate the agent reading the candidate file (grounding it explicitly)
    record_query_success(root, ["src/auth.py"])
    handle_pre_tool_use(
        root,
        {"tool_name": "Read", "tool_input": {"path": "src/auth.py"}},
    )
    assert (
        handle_pre_tool_use(
            root,
            {"tool_name": "Write", "tool_input": {"path": "src/auth.py", "contents": "# ok\n"}},
        ).get("permission")
        == "allow"
    )
    (root / ".cursor/session/chats").mkdir(parents=True, exist_ok=True)
    (root / ".cursor/session/CURRENT_CHAT.md").write_text("chat_id: c_golden\n", encoding="utf-8")
    (root / ".cursor/session/chats/c_golden.md").write_text("# golden\n", encoding="utf-8")
    (root / ".cursor/session/OPEN_CHATS.yaml").write_text(
        "open:\n- id: c_golden\n  goal: golden\n  open_questions: []\n"
        "  files_touched: [src/auth.py]\n  status: active\n",
        encoding="utf-8",
    )
    (root / ".cursor/session/REPO_SESSION.md").write_text(
        "# Repo session\n\n## Decisions\n\nGolden path.\n",
        encoding="utf-8",
    )
    assert run_wrapup(root, HyperConsole(plain=True), no_graph=True) == 0
    report = build_doctor_report(root)
    assert report["memory_index_present"]
    assert _doctor_exit_code(report, tier="ready") == 0


def test_memory_redacts_secrets_on_index(tmp_path):
    """Test memory redacts secrets on index. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".cursor/session").mkdir(parents=True)
    (root / ".cursor/session/REPO_SESSION.md").write_text(
        "# Repo session\n\n## Decisions\n\n"
        "Bearer eyJhbGciOiJIUzI1NiJ9.xyz\n\n"
        "OpenAI sk-abcdefghijklmnopqrstuvwxyz\n",
        encoding="utf-8",
    )
    rebuild_memory_index(root)
    hits = search_memory_index(root, "Decisions", limit=3)
    assert hits
    excerpt = hits[0]["excerpt"]
    assert "eyJhbGci" not in excerpt
    assert "sk-abcdefghijklmnopqrst" not in excerpt


def test_onboard_json_stdout_is_json_only(tmp_path, capsys):
    """Test onboard json stdout is json only. Args: tmp_path, capsys. (hypercharge-managed)"""
    import json
    import subprocess

    from hypercharge.onboard_cmd import run_onboard
    from hypercharge.ui.console import HyperConsole

    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("# test\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    code = run_onboard(
        root,
        HyperConsole(plain=True),
        skip_machine_install=True,
        no_graph=True,
        as_json=True,
    )
    assert code == 0
    out = capsys.readouterr().out.strip()
    assert out.startswith("{")
    json.loads(out)


def test_pre_tool_network_advisory_allows(tmp_path):
    """Network commands always allow + HEADS UP advisory — no audit-log denial written."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".cursor/hypercharge").mkdir(parents=True)
    result = handle_pre_tool_use(
        root, {"tool_name": "Shell", "tool_input": {"command": "curl https://example.com"}}
    )
    assert result.get("permission") == "allow"
    assert result.get("agent_message")
    assert "network" in result["agent_message"].lower() or "HEADS UP" in result["agent_message"]


@pytest.mark.parametrize(
    "cmd,expect_unsafe",
    [
        ("hypercharge doctor --tier ready", False),
        (".venv/bin/python -m pytest tests/ -q", False),
        ("curl https://example.com", True),
        ("wget -O- https://example.com", True),
        ("echo $(whoami)", True),
        ("cat hypercharge/cli.py", False),  # cat is allowlisted safe
    ],
)
def test_shell_gate_matrix(cmd, expect_unsafe, tmp_path):
    """Shell gate: expect_unsafe means network/subshell risk, not hook denial."""
    from hypercharge.shell_gate import assess_shell_command

    root = tmp_path / "repo"
    root.mkdir()
    assessment = assess_shell_command(cmd)
    if expect_unsafe:
        assert not assessment.safe or "network" in assessment.reason or "subshell" in assessment.reason
    else:
        assert assessment.safe


def test_query_sparse_returns_honest_candidates_not_fake_grounding(tmp_path):
    """When graphify returns sparse output, fallback exits 1 with honest candidate list, no fake :N citation."""
    from unittest.mock import patch

    from hypercharge.context import run_grounded_query
    from hypercharge.graph import graphify_out_dir

    root = tmp_path / "repo"
    root.mkdir()
    (root / "hypercharge").mkdir()
    (root / "hypercharge/hook_handlers.py").write_text("def handle_pre_tool_use():\n    pass\n", encoding="utf-8")
    gdir = graphify_out_dir(root)
    gdir.mkdir(parents=True)
    (gdir / "graph.json").write_text(
        json.dumps(
            {
                "nodes": [
                    {"source_file": "hypercharge/hook_handlers.py", "community": 1},
                ],
                "links": [],
            }
        ),
        encoding="utf-8",
    )
    (gdir / ".graphify_labels.json").write_text(
        '{"1": "hypercharge · hook_handlers.py"}',
        encoding="utf-8",
    )

    def sparse_query(*_a, **_k):
        """Sparse query. Returns: subprocess.CompletedProcess(args=[], returncode=0,. (hypercharge-managed)"""
        import subprocess

        return subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="## Module map\n  1: hypercharge · hook_handlers.py\n",
            stderr="",
        )

    with (
        patch("hypercharge.context.ensure_context_ready", return_value=True),
        patch("hypercharge.context.graph_is_present", return_value=True),
        patch("hypercharge.context._run_graphify_query", sparse_query),
    ):
        code, text = run_grounded_query(root, "hook_handlers pre tool use")
    assert code != 0
    assert "hook_handlers.py" in text
    assert "hook_handlers.py:1" not in text
    assert "UNVERIFIED" in text or "candidate" in text.lower() or "no graph citations" in text.lower()


def test_architecture_doc_exists():
    """Test architecture doc exists. (hypercharge-managed)"""
    arch = Path(__file__).resolve().parents[1] / "ARCHITECTURE.md"
    assert arch.is_file()
    text = arch.read_text(encoding="utf-8")
    assert "Golden path" in text
    assert "dev_repo" in text.lower() or "Dev repo" in text
    assert "Hook pipeline" in text


def test_pyproject_has_pytest_cov():
    """Test pyproject has pytest cov. (hypercharge-managed)"""
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    assert "pytest-cov" in text
    assert "[tool.coverage.run]" in text


def test_query_live_exits_zero_when_graph_present():
    """Integration: real repo graph query runs without crashing and names relevant files.

    Exit 0 when graphify returns real path:line citations; exit 1 with honest candidates
    when the graph yields no verified citations — both are correct behaviour.
    """
    import subprocess
    import sys

    repo = Path(__file__).resolve().parents[1]
    from hypercharge.graph import graph_is_present

    if not graph_is_present(repo):
        pytest.skip("graph not present in dev checkout")
    proc = subprocess.run(
        [sys.executable, "-m", "hypercharge", "query", "hook_handlers install_cmd"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert proc.returncode in (0, 1), proc.stdout + proc.stderr
    assert "hook_handlers" in proc.stdout.lower() or "install_cmd" in proc.stdout.lower()


def test_dev_repo_allows_package_writes_without_grounding(tmp_path):
    """Test dev repo allows package writes without grounding. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "hypercharge").mkdir()
    (root / "hypercharge/__init__.py").write_text("", encoding="utf-8")
    (root / "hypercharge/widget.py").write_text("# old\n", encoding="utf-8")
    (root / "pyproject.toml").write_text('[project]\nname = "hypercharge"\n', encoding="utf-8")
    deploy_templates(root)
    from hypercharge.grounding_session import dev_repo_mode

    assert dev_repo_mode(root)
    result = handle_pre_tool_use(
        root,
        {"tool_name": "Write", "tool_input": {"path": "hypercharge/widget.py", "contents": "# new\n"}},
    )
    assert result.get("permission") == "allow"


def test_dev_repo_advises_on_curl(tmp_path):
    """Network commands always allow + HEADS UP advisory — even in dev repos."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "hypercharge").mkdir()
    (root / "hypercharge/__init__.py").write_text("", encoding="utf-8")
    (root / "pyproject.toml").write_text('[project]\nname = "hypercharge"\n', encoding="utf-8")
    deploy_templates(root)
    result = handle_pre_tool_use(
        root, {"tool_name": "Shell", "tool_input": {"command": "curl https://example.com"}}
    )
    assert result.get("permission") == "allow"
    assert result.get("agent_message")
    assert "network" in result["agent_message"].lower() or "HEADS UP" in result["agent_message"]


def test_consumer_repo_advises_ungrounded_write(tmp_path):
    """Consumer repos default to advisory (warn) — an ungrounded write is allowed with
    an advisory message, never denied. Enforcement is opt-in via grounding_gate: block."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src/app.py").write_text("# app\n", encoding="utf-8")
    (root / ".cursor").mkdir()
    deploy_templates(root)
    from hypercharge.grounding_session import dev_repo_mode, grounding_policy

    assert not dev_repo_mode(root)
    assert grounding_policy(root) == "warn"
    result = handle_pre_tool_use(
        root,
        {"tool_name": "Write", "tool_input": {"path": "src/app.py", "contents": "# hack\n"}},
    )
    assert result.get("permission") == "allow"
    assert result.get("agent_message")
    assert "src/app.py" in result["agent_message"] or "hasn't been queried" in result["agent_message"]
