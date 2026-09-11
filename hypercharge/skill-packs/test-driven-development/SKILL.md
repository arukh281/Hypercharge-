---
name: test-driven-development
description: >
  Red-green-refactor for behaviour changes — test the real contract, not implementation trivia.
---

# Test-driven development

## When

- New behaviour or bug fix with clear input/output
- Regressions — write a failing test first when possible

## When to skip full TDD

- Pure copy/docs/config with no logic
- User explicitly said no tests

## Steps

1. **Red** — smallest test that fails for the right reason
2. **Green** — minimal code to pass
3. **Refactor** — clean without changing behaviour

## Good tests

- One assertion theme per test
- Descriptive names: `test_wrapup_advances_maturity_after_compile`
- Use fixtures/temp dirs; no network unless integration test

## Hypercharger

- Tests live in `tests/`; run: `.venv/bin/python -m pytest`
- Mirror CLI patterns from `tests/test_cli.py`

---

*Adapted from [obra/superpowers](https://github.com/obra/superpowers) (MIT, Copyright (c) 2025 Jesse Vincent). Condensed and rewritten for Hypercharge. See ATTRIBUTION.md for the full licence notice.*
