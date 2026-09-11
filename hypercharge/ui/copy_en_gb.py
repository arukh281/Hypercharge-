"""User-facing strings (British English). Plain language first."""

APP_TITLE = "Hypercharge"
APP_TAGLINE = "Hypercharger — your repo assistant in Cursor or Claude Code"

INSTALL_STEPS = [
    "CLI",
    "Graphify (deferred)",
    "Agent skills",
    "Health check",
]

SETUP_STEPS = [
    "Migrate",
    "Templates",
    "Graph",
    "Intent",
    "Inventory",
    "Rules compile",
]

NEXT_SETUP = "In chat, say: install hypercharge (agent runs onboard)"
NEXT_ONBOARD = "Agent: hypercharge onboard --path <git_root>"
NEXT_COMPILE = "Optional: say compile to harden rule precedence and fix conflicts."
NEXT_WRAPUP_CHAT = 'In chat, say: wrap up'
NEXT_WRAPUP_DAY = 'In chat, say: done for the day'

# --- Setup terminal footer (shown after hypercharge setup) ---

SETUP_FOOTER_READY = [
    "This repo is ready.",
    "Synced: hypercharge.mdc + hypercharge-grounding.mdc (always apply).",
    "Created: code map, .cursor/session/, rules list.",
    "Your other .cursor rules were NOT changed.",
    NEXT_WRAPUP_CHAT,
    NEXT_WRAPUP_DAY,
]

SETUP_FOOTER_RULES_REVIEW_DONE = [
    "This repo is ready.",
    "Created: code map, .cursor/session/, rules list.",
    "Rules compile done (optional step).",
    NEXT_WRAPUP_CHAT,
    NEXT_WRAPUP_DAY,
]

WARN_SETUP_NON_INTERACTIVE = (
    "Setup ran without prompts (chat/agent mode). Graph + session rules synced. "
    "Say compile in chat for the optional rules step."
)

WARN_SETUP_DIALOGUE_SKIPPED = (
    "Skipped the optional rules compile prompt. Say compile anytime."
)

PROMPT_APPLY_RULES_REVIEW = (
    "Run rules compile now? Scans for conflicts, hardens precedence, updates agent-map. [y/N]: "
)

# --- Agent chat replies (skill must follow these) ---

AGENT_START_DAY = """
## Start day (immersive — mandatory)

User says **start the day** / **good morning** / `/hypercharge lets start the day`.

**You run (quietly):**
1. `hypercharge wrapup --brief --path <git_root>`
2. `hypercharge wrapup --start-day --json --path <git_root>` (or omit `--json`)

**You say (one flowing story — not a checklist):**
- Warm greeting + date
- Where things stand (from brief: branch, recent work, code map status)
- **One question** if `primary_question` is set — usually "What's today's focus?"
- Do **not** list LE-* ids, done|todo|archive|defer, or "rules compile" unless they ask

**Never say:** Current initiative, REPO_SESSION, loose ends, seedling, sprout.

**After they answer focus:** write `## Current initiative` in REPO_SESSION.md, then work normally.

**Wrap up:** if focus was set this chat, include it in wrapup summary — not "Active work".
"""

AGENT_PRESENTATION = """
## Presenting Hypercharge to the user (mandatory)

You run terminal commands. The user stays in chat.

**While running:** brief progress lines ("Installing…", "Building code map…").
**After finishing:** a short story — what was built, where to open it, one next step.
**Never** paste raw step logs (`[3/6] Graph ... ok`) unless they ask for detail.

Translate terminal output into plain English. British English.
"""

AGENT_REPLY_RULES = """
## How you talk to the user (mandatory)

No internal jargon (seedling, sprout, dialogue gate, inventory batch) unless they ask.

Install + setup in one repo chat = **one seamless story** — install, then setup immediately,
then offer rules compile. Do not make them ask twice.

British English. User stays in chat; you run terminal commands.
"""

AGENT_REPLY_AFTER_INSTALL = """
**Done — Hypercharge is on your machine.**

I installed the CLI and the code-map tool. If we are in a project repo, I will wire that up next
(say **install hypercharge** if I have not already run onboard).

**You do not need the terminal** — I run everything from here.
"""

AGENT_REPLY_AFTER_INSTALL_AND_SETUP = """
**Done — Hypercharge is ready for this repo.**

- **Code map:** built — I can answer structure questions without guessing.
- **Browser maps:** open `.cursor/graphify-out/graph.html` (overview) and `.cursor/graphify-out/GRAPH_TREE.html` (folder tree).
- **Session memory:** `.cursor/session/` — say **wrap up** when this chat ends.
- **Your rules:** not changed.

**One thing:** want **rules compile**? It logs that you reviewed the rules list — almost never edits files.
"""

AGENT_REPLY_AFTER_SETUP = """
**Done — this repo is wired up.**

- **Code map** + browser files in `.cursor/graphify-out/` (see graph.html + GRAPH_TREE.html).
- **Session memory** created; your project rules were **not** changed.
- **Optional:** say **compile** for rules review (setup from chat skips that prompt).

Work normally. **wrap up** = end of chat · **done for the day** = refresh map + save day.
"""

AGENT_REPLY_AFTER_SETUP_RULES_REVIEW = """
**Done.** Repo wired up — code map, session memory, rules list.
**Rules compile done.** Your rules were still not rewritten.
**Next:** work normally. Say **wrap up** / **done for the day** when finished.
"""

AGENT_REPLY_AFTER_WRAPUP_CHAT = """
**Saved** this chat to session memory.
**Next:** new task in a new chat, or continue here.
"""

AGENT_REPLY_AFTER_WRAPUP_DAY = """
**Saved** today's work and refreshed the code map.
**Next:** see you next session.
"""

AGENT_ESCALATION_ASK = """
This looks like it needs **deeper reasoning** ({reason}).
I can call a **{label}** helper subagent, or keep going here with the current model.
**Should I call the subagent?** (yes / no)
"""

AGENT_ESCALATION_DECLINED = """
Staying in this chat — I'll work through it with the current model step by step.
"""
