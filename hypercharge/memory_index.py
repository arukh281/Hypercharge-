"""Keyword memory index — ranked recall over session history (SQLite FTS5 + BM25)."""

from __future__ import annotations

import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from hypercharge.paths import CURSOR_HYPERCHARGE, CURSOR_SESSION

_INDEX_NAME = "memory-index.sqlite"
_CHUNK_MAX = 1200
_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|secret|password|token|credential)\s*[:=]\s*\S+"),
    re.compile(r"(?i)-----BEGIN [A-Z ]+ PRIVATE KEY-----"),
    re.compile(r"(?i)aws[_-]?secret[_-]?access[_-]?key\s*=\s*\S+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),
)


def _redact_secrets(text: str) -> str:
    """Internal _redact_secrets. Args: text. Returns: redacted. (hypercharge-managed)"""
    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def _utc_now() -> str:
    """Internal _utc_now. Returns: datetime.now(timezone.utc).replace(microsecond=0).. (hypercharge-managed)"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def index_path(root: Path) -> Path:
    """Index path. Args: root. Returns: root.resolve() / CURSOR_HYPERCHARGE / _INDEX_NAME. (hypercharge-managed)"""
    return root.resolve() / CURSOR_HYPERCHARGE / _INDEX_NAME


def memory_index_updated_at(root: Path) -> str | None:
    """Memory index updated at. Args: root. Returns: None. (hypercharge-managed)"""
    if not index_path(root).is_file():
        return None
    try:
        conn = _connect(root)
        row = conn.execute(
            "SELECT value FROM memory_meta WHERE key = 'updated_at'"
        ).fetchone()
        conn.close()
        return str(row[0]) if row else None
    except (sqlite3.Error, OSError):
        return None


def memory_index_stale(root: Path) -> bool:
    """True when session files are newer than the memory index."""
    updated = memory_index_updated_at(root)
    if not updated:
        return True
    from datetime import datetime

    try:
        idx_ts = datetime.fromisoformat(updated.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return True
    root = root.resolve()
    latest = 0.0
    for rel in (
        CURSOR_SESSION / "REPO_SESSION.md",
        CURSOR_SESSION / "OPEN_CHATS.yaml",
    ):
        p = root / rel
        if p.is_file():
            latest = max(latest, p.stat().st_mtime)
    chats = root / CURSOR_SESSION / "chats"
    if chats.is_dir():
        for chat in chats.glob("*.md"):
            latest = max(latest, chat.stat().st_mtime)
    return latest > idx_ts + 1.0


def _connect(root: Path) -> sqlite3.Connection:
    """Internal _connect. Args: root. Returns: conn. (hypercharge-managed)"""
    path = index_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
            source,
            path,
            body,
            ts,
            tokenize='porter unicode61'
        )
        """
    )
    # Migrate: if ts column is missing (schema pre-dates this version), drop and recreate
    try:
        conn.execute("SELECT ts FROM memory_fts LIMIT 0")
    except sqlite3.OperationalError:
        conn.execute("DROP TABLE IF EXISTS memory_fts")
        conn.execute(
            """
            CREATE VIRTUAL TABLE memory_fts USING fts5(
                source,
                path,
                body,
                ts,
                tokenize='porter unicode61'
            )
            """
        )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    return conn


def _chunk_text(text: str, *, max_len: int = _CHUNK_MAX) -> list[str]:
    """Internal _chunk_text. Args: text. Returns: chunks. (hypercharge-managed)"""
    text = _redact_secrets(text.strip())
    if not text:
        return []
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if size + len(para) > max_len and buf:
            chunks.append("\n\n".join(buf))
            buf = []
            size = 0
        buf.append(para)
        size += len(para)
    if buf:
        chunks.append("\n\n".join(buf))
    return chunks


def _collect_chunks(root: Path) -> list[tuple[str, str, str]]:
    """Return (source, path, body) tuples to index."""
    root = root.resolve()
    out: list[tuple[str, str, str]] = []

    session = root / CURSOR_SESSION / "REPO_SESSION.md"
    if session.is_file():
        text = session.read_text(encoding="utf-8", errors="replace")
        section = ""
        heading = "REPO_SESSION"
        for line in text.splitlines():
            if line.startswith("## "):
                if section.strip():
                    for chunk in _chunk_text(section):
                        out.append(("session", str(session.relative_to(root)), f"{heading}\n{chunk}"))
                heading = line[3:].strip()
                section = ""
            else:
                section += line + "\n"
        if section.strip():
            for chunk in _chunk_text(section):
                out.append(("session", str(session.relative_to(root)), f"{heading}\n{chunk}"))

    chats_dir = root / CURSOR_SESSION / "chats"
    if chats_dir.is_dir():
        for chat in sorted(chats_dir.glob("*.md")):
            try:
                text = chat.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = str(chat.relative_to(root))
            for chunk in _chunk_text(text):
                out.append(("chat", rel, chunk))

    archive = root / CURSOR_SESSION / "archive"
    if archive.is_dir():
        ttl_cutoff = time.time() - (90 * 86400)
        for doc in sorted(archive.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:100]:
            if doc.stat().st_mtime < ttl_cutoff:
                continue
            try:
                text = doc.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = str(doc.relative_to(root))
            for chunk in _chunk_text(text):
                out.append(("archive", rel, chunk))

    deferred = root / CURSOR_SESSION / "DEFERRED_QUESTIONS.md"
    if deferred.is_file():
        for chunk in _chunk_text(deferred.read_text(encoding="utf-8", errors="replace")):
            out.append(("deferred", str(deferred.relative_to(root)), chunk))

    return out


def append_memory_chunk(root: Path, source: str, path: str, body: str) -> None:
    """Incrementally index one memory chunk."""
    body = _redact_secrets(body.strip())
    if not body:
        return
    conn = _connect(root)
    existing = conn.execute(
        "SELECT 1 FROM memory_fts WHERE source = ? AND path = ? AND body = ? LIMIT 1",
        (source, path, body),
    ).fetchone()
    if existing:
        conn.close()
        return
    ts_val = str(time.time())
    conn.execute(
        "INSERT INTO memory_fts(source, path, body, ts) VALUES (?, ?, ?, ?)",
        (source, path, body, ts_val),
    )
    conn.execute(
        "INSERT OR REPLACE INTO memory_meta(key, value) VALUES (?, ?)",
        ("updated_at", _utc_now()),
    )
    row = conn.execute(
        "SELECT value FROM memory_meta WHERE key = 'append_count'"
    ).fetchone()
    append_count = int(row[0]) if row else 0
    append_count += 1
    conn.execute(
        "INSERT OR REPLACE INTO memory_meta(key, value) VALUES ('append_count', ?)",
        (str(append_count),),
    )
    if append_count % 50 == 0:
        cutoff = time.time() - (90 * 86400)
        conn.execute(
            "DELETE FROM memory_fts WHERE source = 'file-edit' AND CAST(ts AS REAL) < ?",
            (cutoff,),
        )
    conn.commit()
    conn.close()


def append_memory_entry(root: Path, *, path: str, note: str) -> None:
    """Minimal upsert of a single path+note into the FTS5 table (no full rebuild)."""
    append_memory_chunk(root, source="file-edit", path=path, body=note)


def rebuild_memory_index(root: Path) -> int:
    """Rebuild FTS index from session files. Returns chunk count."""
    root = root.resolve()
    conn = _connect(root)
    conn.execute("DELETE FROM memory_fts")
    count = 0
    ts_val = str(time.time())
    for source, path, body in _collect_chunks(root):
        conn.execute(
            "INSERT INTO memory_fts(source, path, body, ts) VALUES (?, ?, ?, ?)",
            (source, path, body, ts_val),
        )
        count += 1
    conn.execute(
        "INSERT OR REPLACE INTO memory_meta(key, value) VALUES (?, ?)",
        ("updated_at", _utc_now()),
    )
    conn.commit()
    conn.close()
    return count


def _build_fts_query(query: str) -> str:
    """Build FTS5 query with phrase match for multi-word queries and per-token prefix matching."""
    tokens = [t for t in re.findall(r"[A-Za-z0-9_]+", query) if len(t) > 2]
    if not tokens:
        return ""
    fts_parts: list[str] = []
    if len(tokens) > 1:
        phrase = re.sub(r'"', " ", query.strip())
        fts_parts.append(f'"{phrase}"')
    for t in tokens[:20]:
        fts_parts.append(f'"{t}"')
        if len(t) >= 5:
            fts_parts.append(f"{t}*")
    return " OR ".join(fts_parts)


def search_memory_index(root: Path, query: str, *, limit: int = 5) -> list[dict[str, str]]:
    """Ranked memory search using FTS5 BM25."""
    query = (query or "").strip()
    if not query or not index_path(root).is_file():
        return []
    fts_query = _build_fts_query(query)
    if not fts_query:
        return []
    conn = _connect(root)
    try:
        rows = conn.execute(
            """
            SELECT source, path, snippet(memory_fts, 2, '[', ']', '…', 24) AS excerpt,
                   bm25(memory_fts) AS rank
            FROM memory_fts
            WHERE memory_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (fts_query, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return []
    conn.close()
    hits: list[dict[str, str]] = []
    for row in rows:
        hits.append(
            {
                "source": row["source"],
                "path": row["path"],
                "excerpt": row["excerpt"],
                "tag": "MEMORY",
            }
        )
    return hits


def format_memory_hits(hits: list[dict[str, str]]) -> list[str]:
    """Format memory hits. Args: hits. Returns: lines. (hypercharge-managed)"""
    lines: list[str] = []
    for h in hits:
        lines.append(f"- {h['path']}: {h['excerpt']} [{h['tag']}]")
    return lines
