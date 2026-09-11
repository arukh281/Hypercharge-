---
name: repo-guardrail
description: >
  Per-repo Hypercharge guardrail for Claude Code — grounding, session, hooks.
  You run commands; user stays in chat.
---

# Repo guardrail (Claude Code)

## Hooks (`.claude/settings.json`)

- **SessionStart** — context packet
- **UserPromptSubmit** — context on prompt submit
- **PostToolUse** (Write|Edit) — auto log + graph queue
- **Stop** — grounding advisory (does not block)

## Commands (you run)

| User says | Run |
|-----------|-----|
| install hypercharge | `hypercharge onboard --path <git_root>` |
| what's going on | `hypercharge wrapup --brief` |
| start day | `hypercharge wrapup --brief` then `hypercharge wrapup --start-day --json` |
| health / doctor | `hypercharge doctor --tier claude-hooks` |
| repo question | `hypercharge knowledge "…" --budget 1500` |
| wrap up | `hypercharge wrapup` |
| done for the day | `hypercharge wrapup --day` |

British English. Short replies.
