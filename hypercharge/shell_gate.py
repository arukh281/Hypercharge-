"""Shell command grounding gate — block ungrounded file access via terminal."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path

# Whole-command safe prefixes (no repo file grounding required)
_SAFE_PREFIXES = (
    # --- hypercharge / graphify ---
    "hypercharge ",
    "python -m hypercharge",
    "python3 -m hypercharge",
    ".venv/bin/python -m hypercharge",
    "graphify ",
    # --- pytest / test runners ---
    "pytest",
    "python -m pytest",
    "python3 -m pytest",
    ".venv/bin/python -m pytest",
    "jest ",
    "vitest ",
    "mocha ",
    "yarn test",
    "npm test",
    "npm run test",
    "cargo test",
    "go test",
    "tox ",
    "nox ",
    # --- package managers ---
    "npm ",
    "npm run",
    "npx ",
    "yarn ",
    "pnpm ",
    "pip ",
    "pip3 ",
    "uv ",
    "poetry ",
    "pipenv ",
    "cargo ",
    "go ",
    "mvn ",
    "gradle ",
    "gem ",
    "bundle ",
    "brew ",
    # --- build systems ---
    "make ",
    "make",
    "cmake ",
    "pdflatex ",
    "latex ",
    "xelatex ",
    "lualatex ",
    "bibtex ",
    "tectonic ",
    # --- Python / Node / scripting runtimes ---
    "python ",
    "python3 ",
    "node ",
    "ts-node ",
    "deno ",
    "ruby ",
    "perl ",
    # --- file reading (non-modifying) ---
    "ls ",
    "ls",
    "ls -",
    "ll ",
    "la ",
    "cat ",
    "head ",
    "tail ",
    "less ",
    "more ",
    "grep ",
    "rg ",
    "ripgrep ",
    "ag ",
    "find ",
    "fd ",
    "wc ",
    "diff ",
    "stat ",
    "tree ",
    "file ",
    # --- docker / containers ---
    "docker build",
    "docker run",
    "docker ps",
    "docker logs",
    "docker inspect",
    "docker images",
    "docker pull",
    "docker-compose ",
    "docker compose ",
    "podman ",
    # --- git (full breadth) ---
    "git status",
    "git log",
    "git rev-parse",
    "git branch",
    "git stash list",
    "git diff",
    "git show",
    "git add",
    "git commit",
    "git push",
    "git pull",
    "git fetch",
    "git checkout",
    "git switch",
    "git merge",
    "git rebase",
    "git tag",
    "git remote",
    "git clone",
    "git init",
    "git reset",
    "git clean",
    # --- shell utilities ---
    "echo ",
    "printf ",
    "env ",
    "printenv ",
    "export ",
    "source ",
    ". ",
    "set ",
    "type ",
    "which ",
    "whereis ",
    "ps ",
    "top ",
    "htop ",
    "kill ",
    "open ",
    "xdg-open ",
    "cp ",
    "mv ",
    "rm ",
    "mkdir ",
    "touch ",
    "zip ",
    "unzip ",
    "tar ",
    "jq ",
    "yq ",
    # --- linters / formatters / type checkers ---
    "eslint ",
    "prettier ",
    "black ",
    "ruff ",
    "mypy ",
    "flake8 ",
    "pylint ",
    "tsc ",
    "typescript ",
    "swc ",
    # --- misc always-safe builtins ---
    "pwd",
    "date",
    "whoami",
    "uname ",
    "cd ",
    "mkdir -p .cursor",
    "mkdir .cursor",
)

_READ_BINARIES = frozenset(
    {
        "cat",
        "head",
        "tail",
        "less",
        "more",
        "grep",
        "egrep",
        "fgrep",
        "rg",
        "ripgrep",
        "awk",
        "sed",
        "wc",
        "file",
        "stat",
        "diff",
        "cmp",
        "strings",
        "nl",
        "od",
        "hexdump",
        "find",
        "fd",
    }
)
_NETWORK_BINARIES = frozenset(
    {"curl", "wget", "nc", "ncat", "netcat", "ssh", "scp", "rsync", "ftp", "sftp"}
)
_WRITE_BINARIES = frozenset(
    {
        "rm",
        "mv",
        "cp",
        "touch",
        "truncate",
        "chmod",
        "chown",
        "tee",
        "install",
    }
)

_PATH_LIKE = re.compile(
    r"(?:^|[\s'\"])([A-Za-z0-9_./\-]+\.[A-Za-z0-9]+|[A-Za-z0-9_./\-]+/[A-Za-z0-9_./\-]+)"
)
_REDIRECT = re.compile(r"(?:>>?)\s*([^\s;|&]+)")


@dataclass(frozen=True)
class ShellAssessment:
    safe: bool
    paths: tuple[str, ...]
    mode: str  # none | read | write | mixed
    reason: str = ""

    @property
    def needs_grounding(self) -> bool:
        """Needs grounding. Returns: not self.safe and len(self.paths) > 0. (hypercharge-managed)"""
        return not self.safe and len(self.paths) > 0


def _normalize_path(raw: str) -> str | None:
    """Internal _normalize_path. Args: raw. Returns: p.lstrip('./'). (hypercharge-managed)"""
    p = raw.strip().strip("'\"")
    if not p or p.startswith("-") or p.startswith("http"):
        return None
    # Shell vars, env assignments, ssh hosts, heredocs — not repo paths.
    if any(ch in p for ch in ("$", "@", "=", "\n", "\r")):
        return None
    if p.startswith("#!"):
        return None
    if p.startswith(">") or p.startswith("2>") or p.startswith("&>"):
        return None
    if p in (".", "..", "/dev/null", "/dev/stdout", "/dev/stderr"):
        return None
    if any(p.startswith(x) for x in ("/tmp/", "/var/", "/usr/", "/opt/", "/etc/")):
        return None
    if "/" not in p and "." not in Path(p).suffix and not p.endswith("/"):
        # extensionless repo files (Makefile, LICENSE, Dockerfile)
        if p.isupper() or p in ("Makefile", "Dockerfile", "LICENSE", "README"):
            return p.lstrip("./")
        return None
    return p.lstrip("./")


def _extract_paths(command: str) -> list[str]:
    """Internal _extract_paths. Args: command. Returns: paths. (hypercharge-managed)"""
    paths: list[str] = []
    seen: set[str] = set()
    for m in _REDIRECT.finditer(command):
        norm = _normalize_path(m.group(1))
        if norm and norm not in seen:
            seen.add(norm)
            paths.append(norm)
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = command.split()
    skip_next = False
    for i, tok in enumerate(tokens):
        if skip_next:
            skip_next = False
            continue
        if ":" in tok and not tok.startswith("-") and "/" in tok:
            _, _, after = tok.partition(":")
            if after:
                norm = _normalize_path(after)
                if norm and norm not in seen:
                    seen.add(norm)
                    paths.append(norm)
        if tok.startswith("-"):
            if tok in ("-i", "--in-place") or tok.startswith("-i"):
                pass
            elif tok in ("-f", "--file", "-e", "--expression"):
                skip_next = True
            continue
        norm = _normalize_path(tok)
        if norm and norm not in seen:
            seen.add(norm)
            paths.append(norm)
    for m in _PATH_LIKE.finditer(command):
        norm = _normalize_path(m.group(1))
        if norm and norm not in seen:
            seen.add(norm)
            paths.append(norm)
    return paths


def _command_mode(command: str, paths: list[str]) -> str:
    """Internal _command_mode. Args: command, paths. Returns: 'mixed'. (hypercharge-managed)"""
    if not paths:
        return "none"
    lowered = command.lower()
    if ">>" in command or re.search(r"(?<![>])>(?![>])", command):
        return "write"
    if re.search(r"\bsed\b.*\s-i", lowered) or "sed -i" in lowered:
        return "write"
    tokens = lowered.split()
    if not tokens:
        return "none"
    binary = Path(tokens[0]).name
    if binary in _WRITE_BINARIES:
        return "write"
    if binary in _READ_BINARIES:
        return "read"
    if "python" in binary and ("open(" in command or "Path(" in command):
        return "read"
    return "mixed"


def _is_safe(command: str) -> bool:
    """Internal _is_safe. Args: command. Returns: False. (hypercharge-managed)"""
    stripped = command.strip()
    if not stripped:
        return True
    lowered = stripped.lower()
    for prefix in _SAFE_PREFIXES:
        if lowered.startswith(prefix.lower()):
            return True
    if lowered in ("pwd", "git status", "git diff --stat"):
        return True
    if re.match(r"^cd\s+", lowered):
        return True
    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", stripped):
        return True
    return False


def _split_compound(command: str) -> list[str]:
    """Internal _split_compound. Args: command. Returns: [p.strip() for p in parts if p.strip()]. (hypercharge-managed)"""
    parts = re.split(r"\s*(?:&&|\|\||;|\||\n)\s*", command)
    return [p.strip() for p in parts if p.strip()]


def assess_shell_command(command: str) -> ShellAssessment:
    """Classify a shell command for grounding requirements."""
    command = (command or "").strip()
    if not command:
        return ShellAssessment(True, (), "none", "empty")

    if re.search(r"\$\(|`", command):
        return ShellAssessment(False, (), "mixed", "subshell — block under policy")

    segments = _split_compound(command)
    if len(segments) > 1:
        all_paths: list[str] = []
        modes: set[str] = set()
        any_unsafe = False
        for seg in segments:
            sub = assess_shell_command(seg)
            if not sub.safe:
                any_unsafe = True
            all_paths.extend(sub.paths)
            if sub.mode != "none":
                modes.add(sub.mode)
        if any_unsafe or all_paths:
            mode = "mixed" if len(modes) > 1 else (next(iter(modes)) if modes else "mixed")
            if not all_paths and any_unsafe:
                return ShellAssessment(False, (), mode, "compound shell — unparsed segment")
            return ShellAssessment(False, tuple(dict.fromkeys(all_paths)), mode, "compound")
        return ShellAssessment(True, (), "none", "compound safe")

    if _is_safe(command):
        return ShellAssessment(True, (), "none", "allowlisted")

    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = command.split()
    if tokens and Path(tokens[0]).name.lower() in _NETWORK_BINARIES:
        return ShellAssessment(False, (), "mixed", "network binary — block under policy")

    paths = _extract_paths(command)
    mode = _command_mode(command, paths)
    if not paths:
        return ShellAssessment(False, (), mode, "unparsed shell — block under policy")

    return ShellAssessment(False, tuple(paths), mode, "repo paths detected")
