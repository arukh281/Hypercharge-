"""Tests for the answer-gate claim-paragraph logic."""

from __future__ import annotations

from hypercharge.answer_gate import assess_answer_text


def test_claim_marker_without_file_path_passes():
    """A paragraph with a claim word but no file-path token must NOT be flagged."""
    text = "The function handles errors gracefully and returns a sensible default."
    result = assess_answer_text(text)
    assert result.ok, f"Expected ok=True, got violations: {result.violations}"


def test_claim_marker_with_file_path_and_no_tag_fails():
    """A paragraph with a claim word AND a file-path token but no grounding tag must fail."""
    text = "The function handles errors in `auth.py` and returns a sensible default."
    result = assess_answer_text(text)
    assert not result.ok, "Expected ok=False — claim + file path without grounding tag should fail"
