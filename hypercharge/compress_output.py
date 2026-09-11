"""Shrink large tool output — Headroom when available, built-in fallback."""

from __future__ import annotations

import json
import re
from pathlib import Path

from hypercharge.headroom_bundle import ensure_headroom
from hypercharge.paths import resolve_hypercharge_source, user_air_gap

_LOSSY_PREFIX = "[LOSSY] "

_LOG_SIGNAL = re.compile(
    r"(?i)(error|exception|traceback|failed|failure|fatal|assertion|warn(?:ing)?|"
    r"panic|segfault|errno|syntaxerror|typeerror|valueerror|keyerror|"
    r"✗|×|FAIL)"
)


def _tag_lossy(text: str, note: str) -> tuple[str, str]:
    """Prefix stdout with [LOSSY] when compression drops evidence."""
    return f"{_LOSSY_PREFIX}{text}", f"{_LOSSY_PREFIX}{note}"


def _extract_headroom_text(result: object) -> str:
    """Normalise Headroom compress() return — CompressResult, dict, or list."""
    messages = getattr(result, "messages", None)
    if messages is None and isinstance(result, dict):
        messages = result.get("messages")
    if not messages:
        return ""
    first = messages[0]
    if isinstance(first, dict):
        return str(first.get("content") or "")
    return str(first)


def _fallback_truncate(text: str, *, max_chars: int) -> tuple[str, str]:
    if len(text) <= max_chars:
        return text, "unchanged"
    head = max_chars * 2 // 3
    tail = max_chars // 3
    note = f"truncated {len(text)} → {head + tail} chars"
    return text[:head] + "\n\n… [hypercharge shrink] …\n\n" + text[-tail:], note


def _dedupe_consecutive_lines(text: str) -> str:
    lines = text.splitlines()
    if len(lines) < 3:
        return text
    out: list[str] = []
    prev: str | None = None
    repeats = 0
    for line in lines:
        if line == prev:
            repeats += 1
            if repeats == 1:
                out.append("… (repeated lines omitted) …")
            continue
        repeats = 0
        prev = line
        out.append(line)
    return "\n".join(out)


def _compress_logs(text: str, *, max_chars: int) -> tuple[str, str] | None:
    lines = text.splitlines()
    if len(lines) < 40:
        return None
    signal = [ln for ln in lines if _LOG_SIGNAL.search(ln)]
    if not signal and len(lines) < 80:
        return None
    head = lines[:8]
    tail = lines[-8:] if len(lines) > 16 else []
    body = signal[: max(20, len(signal))]
    if not body:
        body = lines[:: max(1, len(lines) // 25)][:25]
    parts = head + ["…", f"— {len(lines)} lines —"] + body
    if tail:
        parts.extend(["…"] + tail)
    out = _dedupe_consecutive_lines("\n".join(parts))
    if len(out) >= len(text):
        return None
    if len(out) > max_chars:
        out = out[: max_chars - 40] + "\n… [hypercharge shrink] …\n"
    return _tag_lossy(out, f"log_focus ({len(lines)} lines → {len(out)} chars)")


def compress_text(text: str, *, max_chars: int = 12_000, content_hint: str = "", air_gap: bool | None = None) -> tuple[str, str]:
    """Return (compressed_text, method_note). Deterministic first; Headroom only as fallback."""
    if len(text) <= max_chars:
        return text, "unchanged"

    log_result = _compress_logs(text, max_chars=max_chars)
    if log_result:
        return log_result

    gap = user_air_gap() if air_gap is None else air_gap
    hc = resolve_hypercharge_source()
    if ensure_headroom(hc, air_gap=gap):
        try:
            from headroom import compress  # type: ignore

            messages = [{"role": "user", "content": text}]
            result = compress(messages)
            out = _extract_headroom_text(result)
            if out and len(out) < len(text):
                clipped = out[: max_chars * 2]
                return _tag_lossy(clipped, f"headroom ({len(text)} → {len(clipped)} chars)")
        except Exception:
            pass

    stripped = text.strip()
    if stripped.startswith("[") and content_hint in ("", "json"):
        try:
            data = json.loads(stripped)
            if isinstance(data, list) and len(data) > 20:
                sample = data[:15]
                summary = {
                    "_hypercharge_shrink": True,
                    "total_rows": len(data),
                    "sample": sample,
                    "note": "Full data on disk — ask hypercharge query or read source file",
                }
                out = json.dumps(summary, indent=2)
                if len(out) < len(text):
                    return _tag_lossy(out, f"json_sample ({len(data)} rows → 15)")
        except json.JSONDecodeError:
            pass

    deduped = _dedupe_consecutive_lines(text)
    if len(deduped) < len(text) * 0.85 and len(deduped) <= max_chars:
        return _tag_lossy(deduped, f"dedupe ({len(text)} → {len(deduped)} chars)")

    out, note = _fallback_truncate(text, max_chars=max_chars)
    if note != "unchanged":
        return _tag_lossy(out, note)
    return out, note


def compress_file(path: Path, *, max_chars: int = 12_000) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    hint = "json" if path.suffix.lower() == ".json" else ""
    return compress_text(text, max_chars=max_chars, content_hint=hint)
