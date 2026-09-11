---
name: systematic-debugging
description: >
  Reproduce, isolate, hypothesise, verify — no random edits until you know the failure mode.
---

# Systematic debugging

## Loop

1. **Reproduce** — exact command, input, expected vs actual
2. **Isolate** — narrow to file/function; bisect if needed
3. **Hypothesis** — one likely cause
4. **Experiment** — smallest check (log, breakpoint, test)
5. **Fix** — one change; re-run reproduction
6. **Guard** — regression test if non-trivial

## Anti-patterns

- Shotgun changes across files
- Fixing symptoms without root cause
- Declaring fixed without re-running the failing case

## Hypercharger

- `hypercharge doctor` for environment/session issues
- Read traceback bottom-up; check recent git diff first

---

*Adapted from [obra/superpowers](https://github.com/obra/superpowers) (MIT, Copyright (c) 2025 Jesse Vincent). Condensed and rewritten for Hypercharge. See ATTRIBUTION.md for the full licence notice.*
