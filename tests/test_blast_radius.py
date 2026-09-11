"""Tests for blast radius analysis."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from hypercharge.blast_radius import BlastRadius, analyse, format_for_injection


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_graph(nodes: list[dict], links: list[dict]) -> dict:
    """Internal _make_graph. Args: nodes, links. Returns: {'directed': True, 'multigraph': False, 'graph': {. (hypercharge-managed)"""
    return {"directed": True, "multigraph": False, "graph": {}, "nodes": nodes, "links": links, "hyperedges": []}


def _write_graph(root: Path, data: dict) -> None:
    """Internal _write_graph. Args: root, data. (hypercharge-managed)"""
    out_dir = root / ".cursor" / "graphify-out"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "graph.json").write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# analyse — file with inbound edges
# ---------------------------------------------------------------------------


def test_analyse_finds_dependents():
    """Files that import the target file appear in dependent_files."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        nodes = [
            {"id": "mod_a", "source_file": "auth/middleware.py"},
            {"id": "mod_b", "source_file": "api/routes.py"},
            {"id": "mod_c", "source_file": "utils/helpers.py"},
        ]
        links = [
            # api/routes.py imports auth/middleware.py
            {"relation": "imports", "source": "mod_b", "target": "mod_a"},
            # utils/helpers.py calls auth/middleware.py
            {"relation": "calls", "source": "mod_c", "target": "mod_a"},
        ]
        _write_graph(root, _make_graph(nodes, links))

        br = analyse(root, "auth/middleware.py")

        assert br.file == "auth/middleware.py"
        assert br.callsite_count == 2
        assert "api/routes.py" in br.dependent_files
        assert "utils/helpers.py" in br.dependent_files
        assert br.risk_level == "low"  # 2 <= 2 → low


def test_analyse_correct_risk_medium():
    """3-8 dependents → medium risk."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        target_id = "target_mod"
        nodes = [{"id": target_id, "source_file": "core/engine.py"}]
        for i in range(5):
            nodes.append({"id": f"dep_{i}", "source_file": f"module_{i}.py"})
        links = [
            {"relation": "imports", "source": f"dep_{i}", "target": target_id}
            for i in range(5)
        ]
        _write_graph(root, _make_graph(nodes, links))

        br = analyse(root, "core/engine.py")

        assert br.callsite_count == 5
        assert br.risk_level == "medium"


def test_analyse_correct_risk_high():
    """9+ dependents → high risk."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        target_id = "target_mod"
        nodes = [{"id": target_id, "source_file": "shared/utils.py"}]
        for i in range(10):
            nodes.append({"id": f"dep_{i}", "source_file": f"consumer_{i}.py"})
        links = [
            {"relation": "calls", "source": f"dep_{i}", "target": target_id}
            for i in range(10)
        ]
        _write_graph(root, _make_graph(nodes, links))

        br = analyse(root, "shared/utils.py")

        assert br.callsite_count == 10
        assert br.risk_level == "high"


# ---------------------------------------------------------------------------
# analyse — test file separation
# ---------------------------------------------------------------------------


def test_analyse_separates_test_files():
    """Test files are in test_files; non-test files are in dependent_files."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        nodes = [
            {"id": "target", "source_file": "auth/middleware.py"},
            {"id": "src_a", "source_file": "api/routes.py"},
            {"id": "test_a", "source_file": "tests/test_auth.py"},
            {"id": "test_b", "source_file": "tests/test_middleware.py"},
        ]
        links = [
            {"relation": "imports", "source": "src_a", "target": "target"},
            {"relation": "imports", "source": "test_a", "target": "target"},
            {"relation": "imports", "source": "test_b", "target": "target"},
        ]
        _write_graph(root, _make_graph(nodes, links))

        br = analyse(root, "auth/middleware.py")

        assert "api/routes.py" in br.dependent_files
        assert "tests/test_auth.py" not in br.dependent_files
        assert "tests/test_auth.py" in br.test_files
        assert "tests/test_middleware.py" in br.test_files
        assert br.callsite_count == 3


# ---------------------------------------------------------------------------
# analyse — no dependents
# ---------------------------------------------------------------------------


def test_analyse_no_edges_returns_empty():
    """File with no inbound dependency edges → empty lists, risk_level 'low'."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        nodes = [
            {"id": "standalone", "source_file": "scripts/migrate.py"},
            {"id": "other", "source_file": "other.py"},
        ]
        links = [
            # only outbound from standalone, not inbound
            {"relation": "imports", "source": "standalone", "target": "other"},
        ]
        _write_graph(root, _make_graph(nodes, links))

        br = analyse(root, "scripts/migrate.py")

        assert br.dependent_files == []
        assert br.test_files == []
        assert br.callsite_count == 0
        assert br.risk_level == "low"
        assert "no dependents" in br.summary


# ---------------------------------------------------------------------------
# analyse — missing graph.json
# ---------------------------------------------------------------------------


def test_analyse_missing_graph_returns_unknown():
    """Missing graph.json → BlastRadius with risk_level 'unknown', no crash."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # Deliberately do NOT write graph.json

        br = analyse(root, "hypercharge/cli.py")

        assert br.risk_level == "unknown"
        assert br.dependent_files == []
        assert br.test_files == []
        assert br.callsite_count == 0
        assert "unknown" in br.summary.lower()


# ---------------------------------------------------------------------------
# format_for_injection
# ---------------------------------------------------------------------------


def test_format_for_injection_high_risk_header():
    """High-risk blast radius produces expected headers."""
    br = BlastRadius(
        file="auth/middleware.py",
        dependent_files=["api/routes.py", "middleware/__init__.py"],
        test_files=["tests/test_auth.py", "tests/test_middleware.py"],
        callsite_count=12,
        risk_level="high",
        summary="auth/middleware.py: 12 dependent(s) — high blast radius",
    )
    text = format_for_injection(br)

    assert text.startswith("## Blast radius: auth/middleware.py")
    assert "Risk: HIGH (12 dependent(s))" in text
    assert "api/routes.py" in text
    assert "tests/test_auth.py" in text
    assert "Test coverage:" in text


def test_format_for_injection_zero_dependents():
    """Zero-dependent file renders as standalone."""
    br = BlastRadius(
        file="scripts/seed.py",
        dependent_files=[],
        test_files=[],
        callsite_count=0,
        risk_level="low",
        summary="scripts/seed.py: no dependents found (standalone)",
    )
    text = format_for_injection(br)

    assert "## Blast radius: scripts/seed.py" in text
    assert "standalone" in text.lower() or "LOW" in text


def test_format_for_injection_unknown():
    """Unknown risk produces UNKNOWN header."""
    br = BlastRadius(
        file="some/file.py",
        dependent_files=[],
        test_files=[],
        callsite_count=0,
        risk_level="unknown",
        summary="some/file.py: graph not found — blast radius unknown",
    )
    text = format_for_injection(br)

    assert "UNKNOWN" in text


def test_format_for_injection_truncates_long_dep_list():
    """More than 8 dependents are truncated with a count."""
    deps = [f"module_{i}.py" for i in range(15)]
    br = BlastRadius(
        file="core/base.py",
        dependent_files=deps,
        test_files=[],
        callsite_count=15,
        risk_level="high",
        summary="core/base.py: 15 dependent(s) — high blast radius",
    )
    text = format_for_injection(br)

    assert "+7 more" in text


# ---------------------------------------------------------------------------
# MCP tool integration (smoke test)
# ---------------------------------------------------------------------------


def test_mcp_blast_radius_tool_in_definitions():
    """hypercharge_blast_radius appears in TOOL_DEFINITIONS."""
    from hypercharge.mcp_server import TOOL_DEFINITIONS

    names = {t["name"] for t in TOOL_DEFINITIONS}
    assert "hypercharge_blast_radius" in names


def test_mcp_blast_radius_call_missing_graph():
    """MCP tools/call for hypercharge_blast_radius doesn't crash on missing graph."""
    from unittest.mock import patch
    from hypercharge.mcp_server import handle_request

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        req = {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {
                "name": "hypercharge_blast_radius",
                "arguments": {"file": "hypercharge/cli.py"},
            },
        }
        resp = handle_request(req, root)

    assert resp["id"] == 10
    content = resp["result"]["content"][0]["text"]
    assert "Blast radius" in content
