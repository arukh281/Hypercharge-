"""Sync Python function docstrings — add or refresh when signatures change."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path

from hypercharge.paths import CURSOR_HYPERCHARGE

_MANAGED_TAG = "hypercharge-managed"
_META_FILE = "docstring-meta.json"


def _meta_path(root: Path) -> Path:
    return root / CURSOR_HYPERCHARGE / _META_FILE


def _load_meta(root: Path) -> dict:
    path = _meta_path(root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_meta(root: Path, data: dict) -> None:
    path = _meta_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _sig_hash(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = [a.arg for a in node.args.args]
    ann = ""
    if hasattr(ast, "unparse"):
        try:
            ann = ast.unparse(node.args)
        except Exception:
            ann = ""
    raw = f"{node.name}:{','.join(args)}:{ann}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def _describe(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    name = node.name
    verb = name.replace("_", " ").strip().capitalize() if not name.startswith("_") else f"Internal {name}"
    params = [a.arg for a in node.args.args if a.arg not in ("self", "cls")]
    param_part = f" Args: {', '.join(params)}." if params else ""
    ret_part = ""
    if hasattr(ast, "unparse"):
        for child in ast.walk(node):
            if isinstance(child, ast.Return) and child.value is not None:
                try:
                    ret_part = f" Returns: {ast.unparse(child.value)[:50]}."
                    break
                except Exception:
                    pass
    return f"{verb}.{param_part}{ret_part} ({_MANAGED_TAG})"


def _indent_of(lines: list[str], lineno: int) -> str:
    if lineno < 1 or lineno > len(lines):
        return "    "
    m = re.match(r"^(\s*)", lines[lineno - 1])
    return (m.group(1) if m else "") + "    "


def sync_docstrings(root: Path, rel_path: str, *, dry_run: bool = False) -> tuple[int, list[str]]:
    """Add or update managed docstrings. Returns (count, messages)."""
    root = root.resolve()
    if not rel_path.endswith(".py"):
        return 0, []
    abs_path = root / rel_path
    if not abs_path.is_file():
        return 0, []
    try:
        source = abs_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(rel_path))
    except (SyntaxError, OSError):
        return 0, []

    lines = source.splitlines(keepends=True)
    meta = _load_meta(root)
    file_meta = meta.setdefault(rel_path, {})
    changed = 0

    nodes = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for node in sorted(nodes, key=lambda n: n.lineno, reverse=True):
        if not node.body:
            continue
        key = node.name
        sig = _sig_hash(node)
        doc = ast.get_docstring(node, clean=False)
        prev_sig = file_meta.get(key)
        stale = prev_sig is not None and prev_sig != sig

        if doc and _MANAGED_TAG not in doc:
            file_meta[key] = sig
            continue
        if doc and not stale:
            file_meta[key] = sig
            continue

        indent = _indent_of(lines, node.lineno)
        block = f'{indent}"""{_describe(node)}"""\n'
        first = node.body[0]

        if doc and isinstance(first, ast.Expr):
            start = first.lineno - 1
            end = (first.end_lineno or first.lineno) - 1
            lines[start : end + 1] = [block]
            changed += 1
        elif not doc:
            insert_at = first.lineno - 1
            lines.insert(insert_at, block)
            changed += 1
        file_meta[key] = sig

    if changed and not dry_run:
        abs_path.write_text("".join(lines), encoding="utf-8")
    if changed or file_meta:
        _save_meta(root, meta)

    msgs = [f"{rel_path}: {changed} docstring(s)"] if changed else []
    return changed, msgs


def run_docstrings(
    root: Path,
    *,
    files: list[str] | None = None,
    dry_run: bool = False,
) -> int:
    root = root.resolve()
    targets = list(files or [])
    if not targets:
        console_skip = {".venv", "node_modules", "graphify-out", ".git"}
        targets = [
            str(p.relative_to(root))
            for p in root.rglob("*.py")
            if not any(part in console_skip for part in p.parts)
        ]
    total = 0
    for f in targets:
        n, msgs = sync_docstrings(root, f, dry_run=dry_run)
        total += n
        for m in msgs:
            print(m)
    print(f"docstrings: {total} function(s) synced")
    return 0
