---
name: ask-questions-if-underspecified
description: >
  Before coding or big plans, ask 1–3 sharp questions when requirements are ambiguous.
  Prefer structured choices over open-ended essays.
---

# Ask when underspecified

## When to ask

- Multiple valid approaches with different trade-offs
- Missing scope (which files, which users, which env)
- Destructive or irreversible actions
- Security, auth, or data-handling unclear

## When not to ask

- Obvious from repo conventions or the user's last message
- Small fix with one clear path — just do it
- User said "your call" or gave explicit constraints

## How to ask

- **1–3 questions max**, not a questionnaire
- Offer **2–4 options** when choices are finite (use AskQuestion tool in Cursor when available)
- State your **default** if they do not answer: "I'll assume X unless you want Y"

## Hypercharger

- Do not block `hypercharge onboard` on trivia — infer from repo and doctor output
- Do ask before changing org-wide rules, deleting session data, or force-pushing

---

*Adapted from [Trail of Bits skills](https://github.com/trailofbits/skills), licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Condensed and rewritten for Hypercharge; this file is shared under the same licence.*
