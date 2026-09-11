"""Structured grounding gate — parse query output, require path:line citations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# path:line, path:line:col, backtick-wrapped paths
_PATH_LINE = re.compile(
    r"(?:`([^`\s]+)`|`?)([A-Za-z0-9_./\-]+\.[A-Za-z0-9]+)(?:`?)(?::(\d+))?",
)
_INFERRED_MARK = re.compile(r"(?i)\bINFERRED\b")
_UNVERIFIED_MARK = re.compile(r"(?i)\bUNVERIFIED\b")
_GROUNDED_MARK = re.compile(r"(?i)\bGROUNDED\b")
_MIN_CITATIONS = 1
_MIN_OUTPUT_CHARS = 40
_REQUIRE_LINE_NUMBERS = True


@dataclass(frozen=True)
class GroundingAssessment:
    """Result of assessing graphify query output."""

    exit_code: int
    status: str  # grounded | sparse | unverified
    citation_count: int
    has_inferred: bool
    body: str

    @property
    def is_grounded(self) -> bool:
        return self.exit_code == 0 and self.status == "grounded"


# Cursor code fence: ```12:34:path/to/file.py
_CURSOR_FENCE = re.compile(
    r"```(\d+):(\d+):([^\n`]+)```"
)


def extract_citations(text: str, *, require_line: bool = _REQUIRE_LINE_NUMBERS) -> list[tuple[str, int | None]]:
    """Return unique (path, line) pairs from query output."""
    seen: set[tuple[str, int | None]] = set()
    out: list[tuple[str, int | None]] = []

    for m in _CURSOR_FENCE.finditer(text):
        try:
            start = int(m.group(1))
        except ValueError:
            continue
        path = m.group(3).strip()
        if path:
            key = (path, start)
            if key not in seen:
                seen.add(key)
                out.append(key)

    for m in _PATH_LINE.finditer(text):
        path = (m.group(1) or m.group(2) or "").strip()
        if not path or path.startswith("http"):
            continue
        line_no: int | None = None
        if m.group(3):
            try:
                line_no = int(m.group(3))
            except ValueError:
                line_no = None
        if require_line and line_no is None:
            continue
        key = (path, line_no)
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def validate_citations_exist(root: Path, citations: list[tuple[str, int | None]]) -> list[tuple[str, int | None]]:
    """Keep only citations whose path exists under repo root."""
    valid: list[tuple[str, int | None]] = []
    root = root.resolve()
    for path, line in citations:
        candidate = (root / path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        if candidate.is_file():
            if line is not None:
                try:
                    line_count = sum(1 for _ in candidate.open(encoding="utf-8", errors="replace"))
                    if line < 1 or line > line_count:
                        continue
                except OSError:
                    continue
            valid.append((path, line))
    return valid


def assess_query_output(
    raw: str,
    *,
    proc_returncode: int = 0,
    stderr: str = "",
    root: Path | None = None,
) -> GroundingAssessment:
    """
    Assess graphify query stdout.

    Exit 0 only when verified path:line citations exist on disk.
    Exit 1 on empty, sparse, or subprocess failure.
    """
    text = (raw or "").strip()
    citations = extract_citations(text)

    if proc_returncode != 0:
        err = (stderr or "").strip()
        msg = f"UNVERIFIED — query failed ({err or 'non-zero exit'}). Read source files."
        return GroundingAssessment(1, "unverified", 0, False, msg)

    if root is not None:
        citations = validate_citations_exist(root, citations)

    if not text or len(text) < _MIN_OUTPUT_CHARS:
        msg = (
            "UNVERIFIED — query returned sparse results (no path:line citations). "
            "Read source files and cite path:line before repo claims."
        )
        return GroundingAssessment(1, "sparse", len(citations), False, msg)

    if len(citations) < _MIN_CITATIONS:
        msg = (
            "UNVERIFIED — query output lacks verified path:line citations on disk. "
            f"Found {len(citations)} valid citation(s); need at least {_MIN_CITATIONS}. "
            "Read source files before repo claims."
        )
        return GroundingAssessment(1, "sparse", len(citations), False, msg)

    has_inferred = bool(_INFERRED_MARK.search(text))
    status = "grounded"
    header = "GROUNDED"
    if has_inferred:
        header = "GROUNDED (contains INFERRED edges — verify in source)"
    elif _UNVERIFIED_MARK.search(text):
        header = "PARTIAL"
    elif _GROUNDED_MARK.search(text):
        header = "GROUNDED"

    body = f"{header} — {len(citations)} verified citation(s)\n\n{text}"
    return GroundingAssessment(0, status, len(citations), has_inferred, body)


def format_citation_list(citations: list[tuple[str, int | None]], *, limit: int = 12) -> str:
    lines: list[str] = []
    for path, line in citations[:limit]:
        if line is not None:
            lines.append(f"  - {path}:{line}")
        else:
            lines.append(f"  - {path}")
    if len(citations) > limit:
        lines.append(f"  … +{len(citations) - limit} more")
    return "\n".join(lines)
