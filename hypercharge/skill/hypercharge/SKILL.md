---
name: hypercharge
description: >
  Hypercharger — install hypercharge once; onboard wires repo. When working,
  use graphify query + headroom shrink to save tokens — not every-message injection.
---

# Hypercharger (agent playbook)

**Brand:** Hypercharger = Hypercharge fully wired (machine + repo).

The user says **install hypercharge** — that is the **only** command they need. You do everything else.

They never touch the terminal. Terminal output is **for you**. In chat: a short **story**, not logs.

British English. No jargon (seedling, sprout, dialogue gate).

**Bundled skills:** `hypercharge install` copies the core pack from the package (not the web) — including **hypercharge-concise** for short user replies. Follow hypercharge-concise on every chat turn.

---

## Golden rule

| User says | You run (exactly) |
|-----------|-------------------|
| install hypercharge / install Hypercharger / hypercharge | **Onboard** below — not install alone |
| hypercharge setup (repo already has machine install) | `onboard --skip-machine-install` or `setup` |
| compile | `hypercharge compile --path <git_root>` (asks what will change; use `--dry-run` to preview) |
| wrap up | `hypercharge wrapup --path <git_root>` |
| story (after onboard) | `hypercharge story --path <git_root>` |

**Never** stop after `install` if you are inside a git repo. **Always onboard.**

---

## Onboard (mandatory checklist)

Copy this checklist mentally — do not skip steps.

### Before you run

- [ ] **Git root** — `git rev-parse --show-toplevel` (never `~/.cursor/skills`)
- [ ] **Hypercharge source** — folder with `hypercharge/pyproject.toml` (or `HYPERCHARGE_ROOT`)
- [ ] **Use venv python** — `.venv/bin/python -m hypercharge` (not global `hypercharge` unless sure)

### Commands (one block)

Replace `HC` with the hypercharge package path (e.g. workspace `hypercharge/`).

```bash
HC="<path-to>/hypercharge"
GIT_ROOT="$(git -C "<workspace>" rev-parse --show-toplevel 2>/dev/null || echo "")"
test -d "$HC/.venv" || python3 -m venv "$HC/.venv"
"$HC/.venv/bin/python" -m pip install -e "$HC" -q
if [ -n "$GIT_ROOT" ]; then
  cd "$GIT_ROOT"
  "$HC/.venv/bin/python" -m hypercharge --plain onboard --path "$GIT_ROOT" --json
else
  "$HC/.venv/bin/python" -m hypercharge --plain install
fi
```

Read `--json` manifest or terminal footer yourself. **Do not paste it to the user.**

### After onboard — tell the user (story template)

Read `.cursor/hypercharge/last-onboard.json` if present. Fill in numbers.

> **Done — Hypercharger is ready.**
>
> - I installed the assistant on your machine and wired up this repo.
> - **Code map:** N nodes — I can answer “where does X live?” without guessing.
> - **Open in browser:** `.cursor/graphify-out/graph.html` and `.cursor/graphify-out/GRAPH_TREE.html`
> - **Community names:** written automatically from folder paths (no API key)
> - **Session memory:** `.cursor/session/` — say **wrap up** when we finish.
> - **Your project rules were not changed.**
>
> **One question:** want **rules compile**? I'll scan for conflicting rules, show what I'll change, then harden precedence.

**Do not ask** for an API key to name graph communities — setup names them from code paths automatically; refine with `hypercharge label-communities` if needed.

If they say yes → explain the plan briefly → `hypercharge compile --path <git_root>` → confirm what was written.

If not in a git repo → say machine is ready; onboard will run when they open a project.

---

## Mistakes you must not make

| Mistake | Correct |
|---------|---------|
| User says install → you only run `install` | Run **onboard** (install + setup) |
| User must say setup second | **Never** ask them to — you run setup inside onboard |
| Paste `[3/6] Graph ... ok` | One-line progress while running; story after |
| Run from `~/.cursor/skills` | **Git repo root** only |
| Dump 5000 lines of pytest/graphify | **Shrink** first (below) |
| Guess repo structure | `hypercharge query "…" --budget 1500` then read named files |
| Auto-edit their rules | **Compile** hardens precedence only; does not rewrite user rules (except agent-map rows) |

---

## Graphify + Headroom (while you work — saves tokens)

When the user asks you to **do something**, you go find what to change. Use these **then** — not on every idle message:

| Step | Tool | Why |
|------|------|-----|
| Need where X lives | `hypercharge query "<topic>" --budget 1500` | Replaces reading 20 random files |
| pytest/grep/build dump | `hypercharge shrink --file /tmp/out.txt` | Headroom-style compress — keeps context small |
| Added/moved modules | `graphify update .` | Keeps map accurate |

**CCR pattern:** small digest first → read `path:line` on demand → never paste raw logs.

**Do not** use Headroom proxy / `headroom wrap cursor`.

### What not to compress

- Source files you will cite → read normally
- `graph.json` navigation → use query, not raw paste
- User-facing chat → always plain story

---

## Daily commands (you run)

| User says | Run |
|-----------|-----|
| start the day / good morning | `hypercharge wrapup --brief` then `hypercharge wrapup --start-day --json` — **one immersive story** (see below) |
| what's going on | `hypercharge wrapup --brief --path <git_root>` |
| health check | `hypercharge doctor --path <git_root>` |
| after code edits | `hypercharge log --file <path> --note "…"` |
| new topic | `hypercharge new-chat --goal "…"` |
| done for the day | `hypercharge wrapup --day --path <git_root>` |
Always-on rules: `hypercharge.mdc`, `hypercharge-grounding.mdc`.

---

## Start day (immersive)

See `AGENT_START_DAY` in copy — **one story, one question**, no interrogation grid.

---

## End of session

User says **wrap up** → `hypercharge wrapup` → "Saved this chat to session memory."

User says **done for the day** → `hypercharge wrapup --day` → refreshes code map + browser HTML.
