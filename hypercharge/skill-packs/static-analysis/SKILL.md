---
name: static-analysis
description: >
  Use linters, type checkers, and grep before guessing — fix what tools report on touched code.
---

# Static analysis

## Order

1. Run project linters/typecheck on **changed files**
2. Fix new errors you introduced
3. Do not "fix" unrelated legacy noise unless asked

## Tools (use what the repo has)

- Python: ruff, mypy, pytest
- JS/TS: eslint, tsc
- Read `pyproject.toml`, `package.json`, CI config for the canonical commands

## Grep patterns

- TODO/FIXME in changed code
- `eval`, `exec`, `pickle`, `shell=True`
- Hardcoded passwords, tokens, private keys

## Hypercharger

- After edits: `ReadLints` on touched paths
- Run `pytest` when changing `hypercharge/` or `tests/`

---

*Adapted from [Trail of Bits skills](https://github.com/trailofbits/skills), licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Condensed and rewritten for Hypercharge; this file is shared under the same licence.*
