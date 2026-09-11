"""Track last test run — block 'fixed' claims when tests failed."""

from __future__ import annotations

import re

from pathlib import Path

from hypercharge.grounding_session import load_grounding, save_grounding

_TEST_CMD = re.compile(r"(?i)\b(pytest|python\s+-m\s+pytest|npm\s+test|cargo\s+test|go\s+test)\b")
_FIXED_CLAIM = re.compile(
    r"(?i)\b(fixed|all tests pass|tests pass|green|working now|issue resolved|should work now)\b"
)


def is_test_command(cmd: str) -> bool:
    return bool(_TEST_CMD.search(cmd or ""))


def record_test_result(root: Path, *, cmd: str, exit_code: int) -> None:
    data = load_grounding(root)
    data["last_test"] = {
        "cmd": (cmd or "")[:200],
        "exit_code": int(exit_code),
    }
    save_grounding(root, data)


def last_test_failed(root: Path) -> bool:
    data = load_grounding(root)
    last = data.get("last_test") or {}
    if not isinstance(last, dict):
        return False
    return last.get("exit_code", 0) != 0


def claims_fixed_while_tests_red(text: str, root: Path) -> bool:
    if not last_test_failed(root):
        return False
    return bool(_FIXED_CLAIM.search(text or ""))
