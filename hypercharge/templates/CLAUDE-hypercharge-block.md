# Hypercharge (managed by `hypercharge setup`)

You work in a Hypercharger repo. The user stays in chat — **you** run Hypercharge commands.

**Code map:** run `hypercharge query "<topic>" --budget 1500` before making repo claims, then read the cited `path:line` before editing.
**Session truth:** `.cursor/session/REPO_SESSION.md` and `OPEN_CHATS.yaml`.
**Skill:** `.claude/skills/repo-guardrail/SKILL.md`.

| User says | You run |
|-----------|---------|
| what's going on | `hypercharge wrapup --brief` |
| start day | `hypercharge wrapup --brief` then `hypercharge wrapup --start-day --json` |
| new topic | `hypercharge new-chat --goal "…"` |
| wrap up | `hypercharge wrapup` |
| done for the day | `hypercharge wrapup --day` |
| after edits | `hypercharge log --file <path> --note "…"` |
| teardown | `hypercharge teardown --path <repo>` |

**Same turn as edits:** run `hypercharge log --file <path> --note "…"` before ending the turn.
**Commits:** during plan execution, commit locally after each task/batch; never `git push` without explicit approval. Otherwise ask before committing.

British English. Short replies.
