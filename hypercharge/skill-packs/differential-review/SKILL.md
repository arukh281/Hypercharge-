---
name: differential-review
description: >
  Review only what changed — diff-first, line-level risk, not a full codebase audit.
---

# Differential review

## Focus

- Read the **diff** (branch vs base or unstaged) before reading surrounding files
- Flag issues **in changed lines** first; note pre-existing issues separately if critical

## Checklist per hunk

1. Correctness — does new logic match intent?
2. Edge cases — null, empty, errors, concurrency
3. Security — input, authz, secrets, injection
4. Tests — behaviour change without test?
5. Scope — unrelated churn?

## Output

- **Blockers** — must fix before merge
- **Suggestions** — nice to have
- Keep each finding: file, what, why, fix hint

## Hypercharger

- Prefer `git diff` over re-explaining the whole module
- Do not paste the full diff to the user — summarise findings (see hypercharge-concise)

---

*Adapted from [Trail of Bits skills](https://github.com/trailofbits/skills), licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Condensed and rewritten for Hypercharge; this file is shared under the same licence.*
