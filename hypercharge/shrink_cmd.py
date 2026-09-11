"""CLI: shrink large captured output."""

from __future__ import annotations

from pathlib import Path

from hypercharge.context import shrink_for_context
from hypercharge.ui.console import HyperConsole


def run_shrink(
    console: HyperConsole,
    *,
    text: str = "",
    file: Path | None = None,
    max_chars: int = 12_000,
    air_gap: bool | None = None,
) -> int:
    if file is not None:
        if not file.is_file():
            console.step_fail("Shrink", f"File not found: {file}")
            return 1
        raw = file.read_text(encoding="utf-8", errors="replace")
        hint = "json" if file.suffix.lower() == ".json" else ""
        out, note = shrink_for_context(raw, max_chars=max_chars, content_hint=hint, air_gap=air_gap)
    elif text:
        out, note = shrink_for_context(text, max_chars=max_chars, air_gap=air_gap)
    else:
        console.step_fail("Shrink", "Pass --text or --file")
        return 1

    print(out)
    if note != "unchanged":
        console.warn(f"Shrink: {note}")
    return 0
