"""Answer-time grounding gate — detect repo claims without evidence tags."""

from __future__ import annotations

import re
from dataclasses import dataclass

from pathlib import Path

from hypercharge.grounding_gate import extract_citations, validate_citations_exist

# Behavioural claims about the codebase
_CLAIM_MARKERS = re.compile(
    r"(?i)\b("
    r"the code|this repo|implemented in|located in|defined in|entry point|"
    r"handles|responsible for|calls|imports from|runs when|fails because|"
    r"the function|the class|the module|works by|uses|returns|exports|"
    r"configured in|registered in|wired in|dispatches|delegates"
    r")\b"
)
_PATH_MENTION = re.compile(
    r"`?([A-Za-z0-9_./\-]+\.[A-Za-z0-9]+)`?(?::(\d+))?"
)
_TAG_OK = re.compile(r"\b(GROUNDED|INFERRED|UNVERIFIED)\b")
_SKIP_LINES = re.compile(r"(?i)^(sure|okay|yes|no|done|thanks|got it)")


@dataclass(frozen=True)
class AnswerAssessment:
    violations: list[str]
    claim_count: int
    tagged: bool

    @property
    def ok(self) -> bool:
        """Ok. Returns: len(self.violations) == 0. (hypercharge-managed)"""
        return len(self.violations) == 0


def assess_answer_text(text: str, root: Path | None = None) -> AnswerAssessment:
    """
    Flag assistant text that makes repo claims without GROUNDED/INFERRED/UNVERIFIED
  or path:line citations.
    """
    if not text or len(text.strip()) < 40:
        return AnswerAssessment([], 0, True)

    stripped = text.strip()
    if _SKIP_LINES.match(stripped.splitlines()[0].strip()):
        return AnswerAssessment([], 0, True)

    has_tag = bool(_TAG_OK.search(text))
    citations = extract_citations(text, require_line=True)
    has_citation = len(citations) >= 1

    claim_hits = _CLAIM_MARKERS.findall(text)
    path_hits = _PATH_MENTION.findall(text)
    claim_count = len(claim_hits) + (1 if path_hits else 0)

    if not claim_hits and not path_hits:
        return AnswerAssessment([], 0, has_tag or has_citation)

    # Require tag or path:line per claim paragraph — one tag for whole message is insufficient
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    bad_paras = 0
    for para in paragraphs:
        if not _CLAIM_MARKERS.search(para) or not _PATH_MENTION.search(para):
            continue
        para_tag = bool(_TAG_OK.search(para))
        para_cites = extract_citations(para, require_line=True)
        if root is not None and para_cites:
            para_cites = validate_citations_exist(root, para_cites)
        if root is not None and extract_citations(para, require_line=True) and not para_cites:
            bad_paras += 1
            continue
        if root is not None and para_cites:
            from hypercharge.grounding_session import is_path_grounded

            if not all(is_path_grounded(root, p) for p, _ in para_cites):
                bad_paras += 1
                continue
            # Claim paragraphs need grounded path:line — tags alone are insufficient.
            continue
        if root is not None:
            bad_paras += 1
            continue
        if not para_tag and not para_cites:
            bad_paras += 1

    if bad_paras == 0 and (has_tag or has_citation):
        return AnswerAssessment([], claim_count, True)

    if bad_paras == 0:
        return AnswerAssessment([], claim_count, has_tag or has_citation)

    violations = [
        f"{bad_paras} paragraph(s) with repo claims lack grounded path:line citations."
    ]
    return AnswerAssessment(violations, claim_count, False)


def format_answer_gate_message(assessment: AnswerAssessment) -> str:
    """Format answer gate message. Args: assessment. Returns: '<!-- hypercharge-managed: answer-gate -->\n**Grou. (hypercharge-managed)"""
    if assessment.ok:
        return ""
    return (
        "<!-- hypercharge-managed: answer-gate -->\n"
        "**Grounding reminder:** " + assessment.violations[0]
    )
