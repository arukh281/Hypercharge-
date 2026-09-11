"""Lightweight bundle and built-in shrink."""

from __future__ import annotations

from hypercharge.bundle import load_manifest
from hypercharge.compress_output import compress_text


def test_manifest_has_no_headroom():
    manifest = load_manifest()
    bundled = manifest.get("bundled") or {}
    assert "headroom-ai" not in bundled
    assert "graphifyy" in bundled


def test_compress_log_focus():
    lines = ["ok"] * 200 + ["ERROR: boom", "Traceback (most recent):"] + ["ok"] * 200
    text = "\n".join(lines)
    out, note = compress_text(text, max_chars=800)
    assert len(out) < len(text)
    assert "ERROR" in out
    assert "log_focus" in note


def test_compress_json_sample():
    text = "[" + ",".join(str(i) for i in range(100)) + "]"
    out, note = compress_text(text, max_chars=80, content_hint="json")
    assert "total_rows" in out
    assert "json_sample" in note
