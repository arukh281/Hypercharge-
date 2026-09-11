"""Tests for adaptive context-budget logic in hook_handlers."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from hypercharge.hook_handlers import handle_before_submit_prompt, handle_session_start


# ---------------------------------------------------------------------------
# handle_session_start — adaptive budget
# ---------------------------------------------------------------------------


def _make_runtime(tmp: Path) -> None:
    """Create a minimal runtime.json so handle_session_start proceeds."""
    hc = tmp / ".cursor" / "hypercharge"
    hc.mkdir(parents=True, exist_ok=True)
    (hc / "runtime.json").write_text("{}", encoding="utf-8")


def test_session_start_budget_800_when_no_queried_paths():
    """Fresh session with stale graph → budget=800, lean=False."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_runtime(root)
        with (
            patch(
                "hypercharge.hook_handlers.load_grounding",
                return_value={"queried_paths": []},
            ),
            patch(
                "hypercharge.hook_handlers.graph_stale_reason",
                return_value="missing",
            ),
            patch(
                "hypercharge.hook_handlers.build_context_packet",
                return_value="ctx",
            ) as mock_bcp,
        ):
            handle_session_start(root)

    mock_bcp.assert_called_once_with(root, budget=800, lean=False)


def test_session_start_budget_500_when_graph_fresh():
    """Fresh graph and session → lean packet with budget=500."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_runtime(root)
        with (
            patch(
                "hypercharge.hook_handlers.load_grounding",
                return_value={"queried_paths": []},
            ),
            patch(
                "hypercharge.hook_handlers.graph_stale_reason",
                return_value=None,
            ),
            patch(
                "hypercharge.hook_handlers.build_context_packet",
                return_value="ctx",
            ) as mock_bcp,
        ):
            handle_session_start(root)

    mock_bcp.assert_called_once_with(root, budget=500, lean=True)


def test_session_start_budget_350_when_three_or_more_queried_paths():
    """Grounded session (3+ queried paths) → build_context_packet called with budget=350."""
    paths = ["a.py", "b.py", "c.py"]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_runtime(root)
        with (
            patch(
                "hypercharge.hook_handlers.load_grounding",
                return_value={"queried_paths": paths},
            ),
            patch(
                "hypercharge.hook_handlers.graph_stale_reason",
                return_value=None,
            ),
            patch(
                "hypercharge.hook_handlers.build_context_packet",
                return_value="ctx",
            ) as mock_bcp,
        ):
            handle_session_start(root)

    mock_bcp.assert_called_once_with(root, budget=350, lean=True)


def test_session_start_budget_800_when_two_queried_paths():
    """Two queried paths (< 3) with stale graph → budget=800."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_runtime(root)
        with (
            patch(
                "hypercharge.hook_handlers.load_grounding",
                return_value={"queried_paths": ["a.py", "b.py"]},
            ),
            patch(
                "hypercharge.hook_handlers.graph_stale_reason",
                return_value="predates_commit",
            ),
            patch(
                "hypercharge.hook_handlers.build_context_packet",
                return_value="ctx",
            ) as mock_bcp,
        ):
            handle_session_start(root)

    mock_bcp.assert_called_once_with(root, budget=800, lean=False)


# ---------------------------------------------------------------------------
# handle_before_submit_prompt — short prompt skips grounding digest
# ---------------------------------------------------------------------------


def _make_payload(prompt: str) -> dict:
    """Internal _make_payload. Args: prompt. Returns: {'prompt': prompt}. (hypercharge-managed)"""
    return {"prompt": prompt}


def test_short_prompt_skips_grounding_digest():
    """Prompt shorter than 20 chars → build_prompt_grounding_digest never called."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_runtime(root)
        with (
            patch("hypercharge.hook_handlers.build_turn_delta", return_value=""),
            patch(
                "hypercharge.hook_handlers.build_prompt_grounding_digest"
            ) as mock_digest,
        ):
            handle_before_submit_prompt(root, _make_payload("ok"))

    mock_digest.assert_not_called()


def test_empty_prompt_skips_grounding_digest():
    """Empty prompt → build_prompt_grounding_digest never called."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_runtime(root)
        with (
            patch("hypercharge.hook_handlers.build_turn_delta", return_value=""),
            patch(
                "hypercharge.hook_handlers.build_prompt_grounding_digest"
            ) as mock_digest,
        ):
            handle_before_submit_prompt(root, _make_payload(""))

    mock_digest.assert_not_called()


def test_medium_prompt_uses_budget_350():
    """Prompt between 20-200 chars → digest called with budget=350."""
    prompt = "Fix the login bug in auth module"  # 33 chars
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_runtime(root)
        with (
            patch("hypercharge.hook_handlers.build_turn_delta", return_value=""),
            patch(
                "hypercharge.hook_handlers.build_prompt_grounding_digest",
                return_value="grounding",
            ) as mock_digest,
        ):
            handle_before_submit_prompt(root, _make_payload(prompt))

    mock_digest.assert_called_once_with(root, prompt, budget=350)


def test_long_prompt_uses_budget_600():
    """Prompt over 200 chars → digest called with budget=600."""
    prompt = "x" * 201
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_runtime(root)
        with (
            patch("hypercharge.hook_handlers.build_turn_delta", return_value=""),
            patch(
                "hypercharge.hook_handlers.build_prompt_grounding_digest",
                return_value="grounding",
            ) as mock_digest,
        ):
            handle_before_submit_prompt(root, _make_payload(prompt))

    mock_digest.assert_called_once_with(root, prompt, budget=600)
