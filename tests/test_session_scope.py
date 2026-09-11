"""Per-session state namespacing (session_scope + path helpers)."""

from __future__ import annotations

import pytest

from hypercharge import session_scope
from hypercharge.grounding_session import grounding_path
from hypercharge.turn_tracker import _state_path


@pytest.fixture(autouse=True)
def _reset_session_scope():
    """The session id is a process global — never let it leak between tests."""
    session_scope.set_session_id(None)
    yield
    session_scope.set_session_id(None)


def test_no_session_uses_shared_path(tmp_path):
    session_scope.set_session_id(None)
    p = grounding_path(tmp_path)
    assert p.name == "session-grounding.json"
    assert p.parent.name == "hypercharge"


def test_session_id_namespaces_both_state_files(tmp_path):
    session_scope.set_session_id("win-1")
    try:
        g = grounding_path(tmp_path)
        s = _state_path(tmp_path)
        assert g.parent.name == "win-1" and g.parent.parent.name == "sessions"
        assert s.parent.name == "win-1" and s.parent.parent.name == "sessions"
    finally:
        session_scope.set_session_id(None)


def test_distinct_sessions_get_distinct_files(tmp_path):
    session_scope.set_session_id("a")
    pa = grounding_path(tmp_path)
    session_scope.set_session_id("b")
    pb = grounding_path(tmp_path)
    session_scope.set_session_id(None)
    assert pa != pb


def test_hostile_id_cannot_escape_sessions_dir(tmp_path):
    for hostile in ("..", "../../etc/passwd", "/", "."):
        session_scope.set_session_id(hostile)
        p = grounding_path(tmp_path).resolve()
        slug = session_scope.session_slug()
        session_scope.set_session_id(None)
        if slug is None:
            # Falls back to the shared path — never a scoped one.
            assert grounding_path(tmp_path).parent.name == "hypercharge"
            continue
        sessions_root = (tmp_path / ".cursor/hypercharge/sessions").resolve()
        assert str(p).startswith(str(sessions_root) + "/")
        assert "/" not in slug and slug not in ("..", ".")


def test_env_var_fallback(tmp_path, monkeypatch):
    session_scope.set_session_id(None)
    monkeypatch.setenv("HYPERCHARGE_SESSION_ID", "envsess")
    try:
        assert session_scope.session_slug() == "envsess"
    finally:
        monkeypatch.delenv("HYPERCHARGE_SESSION_ID", raising=False)
