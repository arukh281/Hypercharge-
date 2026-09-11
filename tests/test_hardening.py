"""Regression guards for redesign fixes that were correct but previously untested."""

from __future__ import annotations

import importlib

import pytest

from hypercharge.hook_handlers import handle_after_file_edit


def test_after_edit_never_mutates_source(tmp_path):
    """P0-5: the after-edit hook must not rewrite the edited source file.

    The old code ran docstring sync from the hook, inserting managed docstrings into
    functions and invalidating the read-before-write hash. A function with no docstring
    is the exact case the old sync would have mutated.
    """
    root = tmp_path / "repo"
    (root / "hypercharge").mkdir(parents=True)
    target = root / "hypercharge/foo.py"
    original = "def compute(x, y):\n    return x + y\n"
    target.write_text(original, encoding="utf-8")

    handle_after_file_edit(root, {"tool_name": "Write", "file_path": "hypercharge/foo.py"})

    assert target.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("mod", ["hypercharge.feedback_cmd", "hypercharge.frustration_detector"])
def test_privacy_subsystem_modules_removed(mod):
    """S3: the prompt-logging/feedback modules are gone, not merely unwired."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(mod)


@pytest.mark.parametrize("cmd", ["feedback", "compile-feedback"])
def test_cli_has_no_feedback_subcommands(cmd):
    """S3: the feedback CLI surface is gone (no way to push prompt snippets)."""
    from hypercharge.cli import build_parser

    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([cmd])
