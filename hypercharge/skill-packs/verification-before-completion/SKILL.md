---
name: verification-before-completion
description: >
  Do not claim done until you ran the relevant check — tests, lint, or manual repro.
---

# Verification before completion

## Before "done" or "fixed"

- Ran the **same command** that failed (or equivalent)
- Linters clean on **files you changed**
- New/changed behaviour has a test when the repo tests similar things

## Evidence

- State what you ran: `pytest tests/test_foo.py -q` → pass
- If you could not run something, say **UNVERIFIED** and what is left

## Hypercharger

- After CLI changes: `pytest` in repo `.venv`
- After onboard/setup changes: dry-run or doctor when feasible
- User sees outcomes, not log dumps (hypercharge-concise)

---

*Adapted from [obra/superpowers](https://github.com/obra/superpowers) (MIT, Copyright (c) 2025 Jesse Vincent). Condensed and rewritten for Hypercharge. See ATTRIBUTION.md for the full licence notice.*
