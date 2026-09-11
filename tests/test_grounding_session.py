"""Session grounding persistence."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from hypercharge.grounding_session import load_grounding, record_query_success, save_grounding


def test_save_grounding_roundtrip(tmp_path: Path) -> None:
    """Test save grounding roundtrip. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    data = load_grounding(root)
    assert save_grounding(root, data) is True
    assert grounding_path(root).is_file()


def test_save_grounding_survives_permission_error(tmp_path: Path) -> None:
    """Test save grounding survives permission error. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()
    data = load_grounding(root)

    with patch(
        "hypercharge.paths.atomic_write_json",
        side_effect=PermissionError(1, "Operation not permitted"),
    ):
        assert save_grounding(root, data) is False


def test_record_query_success_survives_write_block(tmp_path: Path) -> None:
    """Test record query success survives write block. Args: tmp_path. (hypercharge-managed)"""
    root = tmp_path / "repo"
    root.mkdir()

    with patch(
        "hypercharge.paths.atomic_write_json",
        side_effect=PermissionError(1, "Operation not permitted"),
    ):
        record_query_success(root, ["src/foo.py"])  # must not raise

    assert load_grounding(root)["queried_paths"] == []


def test_atomic_write_json_roundtrip_no_temp_left(tmp_path: Path) -> None:
    """Atomic write produces valid JSON and leaves no temp file behind."""
    import json

    from hypercharge.paths import atomic_write_json

    target = tmp_path / "sub" / "state.json"
    atomic_write_json(target, {"a": 1, "b": [1, 2, 3]})
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1, "b": [1, 2, 3]}
    assert list(target.parent.glob(".hc-tmp-*")) == []


def test_atomic_write_json_cleans_up_on_failure(tmp_path: Path) -> None:
    """A serialisation failure leaves neither a partial target nor a temp file."""
    import pytest

    from hypercharge.paths import atomic_write_json

    target = tmp_path / "state.json"
    with pytest.raises(TypeError):
        atomic_write_json(target, {"bad": object()})
    assert not target.exists()
    assert list(tmp_path.glob(".hc-tmp-*")) == []


def grounding_path(root: Path) -> Path:
    """Grounding path. Args: root. Returns: gp(root). (hypercharge-managed)"""
    from hypercharge.grounding_session import grounding_path as gp

    return gp(root)
