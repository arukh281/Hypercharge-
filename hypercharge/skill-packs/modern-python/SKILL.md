---
name: modern-python
description: >
  Python 3.11+ idioms — pathlib, typing, dataclasses, match sparingly, no legacy patterns.
---

# Modern Python

## Prefer

- `pathlib.Path` over `os.path`
- Type hints on public functions; `from __future__ import annotations`
- `dataclass` / `TypedDict` for structured data
- `subprocess.run(..., check=True, capture_output=True)` with explicit encoding
- Context managers for files and locks
- `raise ... from exc` when re-raising

## Avoid

- `typing.List`/`Dict` (use `list`, `dict`)
- Bare `except:` — catch specific exceptions
- Mutable default arguments
- Global mutable state for request/session data

## Hypercharger repo

- CLI via `argparse` subcommands in `hypercharge/cli.py`
- British English in user-facing strings (`hypercharge/ui/copy_en_gb.py`)
- Keep modules small; match existing naming in the file you edit

---

*Adapted from [Trail of Bits skills](https://github.com/trailofbits/skills), licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Condensed and rewritten for Hypercharge; this file is shared under the same licence.*
