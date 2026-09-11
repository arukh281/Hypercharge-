"""Context stack — graphify query + shrink."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from hypercharge.context import run_grounded_query, shrink_for_context


def test_shrink_for_context_never_raises():
    big = "x" * 50_000
    out, note = shrink_for_context(big, max_chars=1000)
    assert len(out) <= 1100
    assert note


def test_grounded_query_installs_graphify(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "main.py").write_text("print('hi')\n", encoding="utf-8")

    hc = Path(__file__).resolve().parents[1]
    calls: list[str] = []

    def fake_ensure(*_a, **_k):
        calls.append("ensure")
        return True

    def fake_present(_root):
        return True

    def fake_query(*_a, **_k):
        import subprocess

        return subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=(
                "GROUNDED digest:\n"
                "- main.py:1 entry point prints hi\n"
                "- main.py:2 additional line for length padding here and more context.\n"
            ),
            stderr="",
        )

    with (
        patch("hypercharge.context.ensure_context_ready", fake_ensure),
        patch("hypercharge.context.graph_is_present", fake_present),
        patch("hypercharge.context._run_graphify_query", fake_query),
    ):
        code, text = run_grounded_query(root, "entry point")
    assert code == 0
    assert "main.py" in text
    assert calls == ["ensure"]


def test_hook_query_never_builds_when_graph_missing(tmp_path):
    """build=False (hook/advisory path) must never trigger a synchronous graph build."""
    root = tmp_path / "repo"
    root.mkdir()

    def boom(*_a, **_k):
        raise AssertionError("run_graphify_build must not be called on the advisory path")

    with (
        patch("hypercharge.context.graphify_available", lambda *_a, **_k: True),
        patch("hypercharge.context.graph_is_present", lambda *_a, **_k: False),
        patch("hypercharge.context.ensure_context_ready", boom),
        patch("hypercharge.context.run_graphify_build", boom),
    ):
        code, text = run_grounded_query(root, "where is the login handler", build=False)
    assert code == 1
    assert text == ""


def test_hook_query_no_rebuild_on_sparse_result(tmp_path):
    """build=False with a present graph queries it but never rebuilds on a sparse result."""
    import subprocess

    root = tmp_path / "repo"
    root.mkdir()

    def boom(*_a, **_k):
        raise AssertionError("run_graphify_build must not be called on the advisory path")

    def sparse_query(*_a, **_k):
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    with (
        patch("hypercharge.context.graphify_available", lambda *_a, **_k: True),
        patch("hypercharge.context.graph_is_present", lambda *_a, **_k: True),
        patch("hypercharge.context._run_graphify_query", sparse_query),
        patch("hypercharge.context.run_graphify_build", boom),
    ):
        code, _text = run_grounded_query(root, "where is the login handler", build=False)
    assert code == 1
