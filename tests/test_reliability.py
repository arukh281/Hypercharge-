"""Doctor, templates deploy cleanup, context failure paths."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from hypercharge.context import run_grounded_query, shrink_for_context
from hypercharge.doctor_cmd import _doctor_exit_code, build_doctor_report
from hypercharge.session import load_lock, save_lock
from hypercharge.runtime_paths import write_runtime_manifest
from hypercharge.graph import graphify_out_dir
from hypercharge.templates_deploy import deploy_templates


def _healthy_repo(root: Path) -> None:
    """Internal _healthy_repo. Args: root. (hypercharge-managed)"""
    gdir = graphify_out_dir(root)
    gdir.mkdir(parents=True, exist_ok=True)
    (gdir / "graph.json").write_text('{"nodes": [], "links": []}', encoding="utf-8")
    session = root / ".cursor/session/REPO_SESSION.md"
    session.write_text("# Repo session\n\n## Current initiative\n\nShip widget.\n", encoding="utf-8")
    lock = load_lock(root)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    lock["last_day_wrapup"] = now
    lock["last_chat_wrapup"] = now
    save_lock(root, lock)
    write_runtime_manifest(root, hc_root=Path(__file__).resolve().parents[1])
    from hypercharge.memory_index import rebuild_memory_index

    rebuild_memory_index(root)


def test_doctor_exit_zero_when_healthy():
    """Test doctor exit zero when healthy. (hypercharge-managed)"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text("# test\n")
        deploy_templates(root)
        _healthy_repo(root)
        report = build_doctor_report(root)
        assert report["loose_ends"] == 0
        assert _doctor_exit_code(report) == 0


def test_deploy_installs_hooks_preserves_custom():
    """Test deploy installs hooks preserves custom. (hypercharge-managed)"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        hooks_dir = root / ".cursor/hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "custom.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        (root / ".cursor/hooks.json").write_text(
            '{"version":1,"hooks":{"beforeShellExecution":[{"command":".cursor/hooks/custom.sh"}]}}',
            encoding="utf-8",
        )
        live = root / ".cursor/hypercharge/LIVE_CONTEXT.md"
        live.parent.mkdir(parents=True, exist_ok=True)
        live.write_text("stale", encoding="utf-8")
        deploy_templates(root)
        assert not live.is_file()
        data = json.loads((root / ".cursor/hooks.json").read_text(encoding="utf-8"))
        assert any(h["command"] == ".cursor/hooks/custom.sh" for h in data["hooks"]["beforeShellExecution"])
        assert (hooks_dir / "hypercharge-session-start.sh").is_file()


def test_grounded_query_unverified_when_graphify_missing(tmp_path):
    """Test grounded query unverified when graphify missing. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    with patch("hypercharge.context.ensure_context_ready", return_value=False):
        code, text = run_grounded_query(root, "entry")
    assert code == 1
    assert "UNVERIFIED" in text


def test_grounded_query_build_failure(tmp_path):
    """Test grounded query build failure. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    with (
        patch("hypercharge.context.ensure_context_ready", return_value=True),
        patch("hypercharge.context.graph_is_present", return_value=False),
        patch("hypercharge.context.run_graphify_build", return_value=(False, "boom")),
    ):
        code, text = run_grounded_query(root, "entry")
    assert code == 1
    assert "boom" in text


def test_shrink_fallback_on_exception():
    """Test shrink fallback on exception. (hypercharge-managed)"""
    with patch("hypercharge.context.compress_text", side_effect=RuntimeError("nope")):
        out, note = shrink_for_context("x" * 5000, max_chars=100)
    assert len(out) <= 1100
    assert note == "fallback"


def test_air_gap_config_roundtrip(tmp_path, monkeypatch):
    """Test air gap config roundtrip. Args: tmp_path, monkeypatch. (hypercharge-managed)"""
    from hypercharge.install_cmd import _write_config
    from hypercharge.paths import user_air_gap

    cfg_home = tmp_path / ".config" / "hypercharge"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    _write_config(air_gap=True)
    assert user_air_gap() is True
    _write_config(air_gap=False)  # reinstall without flag should preserve True
    assert user_air_gap() is True


def test_doctor_cli_exit_zero_when_healthy():
    """Test doctor cli exit zero when healthy. (hypercharge-managed)"""
    import subprocess
    import sys

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text("# test\n")
        deploy_templates(root)
        _healthy_repo(root)
        proc = subprocess.run(
            [sys.executable, "-m", "hypercharge", "--plain", "doctor", "--json", "--path", str(root)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert json.loads(proc.stdout)["loose_ends"] == 0


def test_setup_status_matches_doctor_exit():
    """Test setup status matches doctor exit. (hypercharge-managed)"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text("# test\n")
        deploy_templates(root)
        _healthy_repo(root)
        from hypercharge.doctor_cmd import run_doctor
        from hypercharge.memory_index import rebuild_memory_index
        from hypercharge.status_cmd import run_status
        from hypercharge.ui.console import HyperConsole

        rebuild_memory_index(root)
        console = HyperConsole(plain=True)
        doc_code = run_doctor(root, console, as_json=True)
        st_code = run_status(root, console, as_json=True)
        assert doc_code == st_code == 0
