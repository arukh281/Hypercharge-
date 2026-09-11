---
name: repo-guardrail
description: >
  Per-repo Hypercharge guardrail — see bundled skill/hypercharge/SKILL.md for full
  install/setup presentation. You run commands; user stays in chat.
---

# Repo guardrail

Full chat-first playbook: `hypercharge/skill/hypercharge/SKILL.md` (installed to `~/.cursor/skills/hypercharge`).

**Always-on rules** (synced by `hypercharge setup`):

- `hypercharge.mdc` — session, wrapup, escalation
- `hypercharge-grounding.mdc` — graph query, grounding, shrink

## Commands (you run)

| User says | Run |
|-----------|-----|
| hypercharge setup | `hypercharge setup --path <repo_root>` |
| compile / rules compile | `hypercharge compile --path <repo_root>` |
| start day / startday | `hypercharge wrapup --brief` then `hypercharge wrapup --start-day --json` |
| what's going on | `hypercharge wrapup --brief` |
| health / doctor | `hypercharge doctor` |
| wrap up | `hypercharge wrapup` |
| done for the day | `hypercharge wrapup --day` |
| repo question | `hypercharge knowledge "…" --budget 1500` |

Present terminal results as a short story — never dump raw logs. British English.
