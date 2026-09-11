"""Verify a behavioural claim against file evidence."""

from __future__ import annotations

import re
from pathlib import Path

from hypercharge.grounding_gate import extract_citations
from hypercharge.grounding_session import normalize_repo_path

_TOKEN = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]{2,}")


def _line_text(root: Path, path: str, line: int | None) -> str:
    norm = normalize_repo_path(root, path)
    if not norm:
        return ""
    abs_path = root.resolve() / norm
    if not abs_path.is_file():
        return ""
    lines = abs_path.read_text(encoding="utf-8", errors="replace").splitlines()
    if line is None or line < 1 or line > len(lines):
        return "\n".join(lines[:80])
    start = max(0, line - 3)
    end = min(len(lines), line + 2)
    return "\n".join(lines[start:end])


def _overlap_score(claim: str, evidence: str) -> float:
    claim_tokens = {t.lower() for t in _TOKEN.findall(claim)}
    evidence_tokens = {t.lower() for t in _TOKEN.findall(evidence)}
    if not claim_tokens:
        return 0.0
    return len(claim_tokens & evidence_tokens) / len(claim_tokens)


def verify_claim(root: Path, claim: str, evidence: str) -> tuple[bool, str]:
    """
    evidence: path:line or path:line-line, or free text with citations.
    Returns (ok, message).
    """
    root = root.resolve()
    claim = (claim or "").strip()
    evidence = (evidence or "").strip()
    if not claim:
        return False, "claim is empty"
    cites = extract_citations(evidence, require_line=False)
    if not cites and ":" in evidence:
        m = re.match(r"([^\s:]+):(\d+)(?:-(\d+))?", evidence.strip())
        if m:
            cites = [(m.group(1), int(m.group(2)))]
    if not cites:
        return False, "no path:line evidence — use --evidence src/foo.py:42"
    chunks: list[str] = []
    for path, line in cites:
        norm = normalize_repo_path(root, path)
        if not (root / norm).is_file():
            return False, f"evidence path missing: {norm}"
        chunks.append(_line_text(root, norm, line))
    merged = "\n".join(chunks)
    score = _overlap_score(claim, merged)
    if score < 0.08:
        return False, f"claim does not match evidence at cited lines (overlap={score:.2f})"
    return True, f"verified (overlap={score:.2f})"


def run_verify(root: Path, *, claim: str, evidence: str) -> int:
    ok, msg = verify_claim(root, claim, evidence)
    print(msg)
    return 0 if ok else 1
