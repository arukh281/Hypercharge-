# Hypercharge

**Hypercharge** wires your git repo so Cursor or Claude Code agents work smarter: a live code map, session memory, and safety hooks — **no separate LLM API key required**.

> You talk in chat. The agent runs Hypercharge commands. You do not need to memorise the CLI.

---

## What it does

- Builds a **code graph** of your repo so the agent knows where things live before editing
- Keeps **session memory** across chats — goals, decisions, and loose ends
- Deploys **hook pipelines** into Cursor or Claude Code that **advise** on ungrounded shell/file access (always allow; inject context)
- Runs a **daily briefing** and wrapup to keep context fresh

---

## Installation

### Step 1 — Clone this repo

```bash
git clone https://github.com/arukh281/Hypercharge-.git
cd Hypercharge-
```

### Step 2 — Install the CLI (once per machine)

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .
```

Verify it works:

```bash
hypercharge --version
```

### Step 3 — Wire it into your project

Navigate to **your own repo** (not this one) and run:

```bash
cd /path/to/your-project

# For Cursor + Claude Code (recommended)
hypercharge onboard --path . --target both

# For Claude Code only
hypercharge onboard --path . --target claude

# For Cursor only
hypercharge onboard --path . --target cursor
```

This builds the code map, deploys hooks, and sets up session files. It takes about 30 seconds.

### Step 4 — Check it worked

```bash
hypercharge doctor
```

All green means you're ready.

---

## Using it

Open your project in **Cursor** or **Claude Code** and just talk normally.

| You say | What happens |
|---------|--------------|
| *"Fix the login bug"* | Agent checks the code map, reads the right files, edits |
| *"What's going on?"* | Briefing on session state and recent work |
| *"Start day"* | Morning review of open threads and loose ends |
| *"New topic — refactor the API"* | Fresh chat thread with a tracked goal |
| *"Wrap up"* | Saves this chat to session memory |
| *"Done for the day"* | Day wrapup — refreshes code map and memory index |

You do **not** need to run `query`, `graphify`, or `shrink` yourself — the agent handles all of that.

---

## What gets wired per target

| Target | Cursor | Claude Code |
|--------|--------|-------------|
| `cursor` | `.cursor/rules/*.mdc`, hooks | — |
| `claude` | — | `.claude/settings.json` hooks, `CLAUDE.md`, repo guardrail skill |
| `both` | Full Cursor wiring | Full Claude wiring |

---

## Useful commands

| Command | When |
|---------|------|
| `hypercharge onboard --path . --target both` | First-time setup on a repo |
| `hypercharge setup --path . --target both` | Re-wire after updating Hypercharge |
| `hypercharge doctor` | Health check |
| `hypercharge wrapup --brief` | See what's going on right now |
| `hypercharge wrapup --start-day` | Morning loose-ends review |
| `hypercharge wrapup` | End of chat |
| `hypercharge wrapup --day` | End of day — rebuilds memory index |
| `hypercharge teardown --path .` | Remove Hypercharge wiring (`--target cursor\|claude\|both`; use `both` to remove session + graph too) |

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Agent advises querying before file reads | Expected on first run — hooks inject context; run `hypercharge knowledge` before editing unfamiliar paths |
| `Hypercharge runtime missing` | Run `hypercharge setup --path . --target both` in your repo root |
| Graph missing / stale answers | Run `hypercharge wrapup --day` |
| Claude hooks not firing | Run `hypercharge doctor --tier claude-hooks` |

---

## Requirements

- Python 3.11+
- Cursor or Claude Code (or both)
- Any git repo you want to work in

---

Technical detail: [ARCHITECTURE.md](ARCHITECTURE.md)

## Status

Alpha (v0.1.0). Tested on macOS (Apple Silicon) with Python 3.11+. Linux and Windows are untested.

## Licence and credits

Hypercharge is released under the MIT licence (see `LICENCE`). Copyright (c) 2026 Aradhya Khandelwal.

- Code maps are built with [graphify](https://pypi.org/project/graphifyy/) and tree-sitter, installed from PyPI on first `setup`. They keep their own licences.
- Some bundled skills are adapted from [Trail of Bits skills](https://github.com/trailofbits/skills) (CC BY-SA 4.0) and [obra/superpowers](https://github.com/obra/superpowers) (MIT). See `hypercharge/skill-packs/ATTRIBUTION.md`.
