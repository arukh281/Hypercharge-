"""Start or resume an isolated chat thread."""

from __future__ import annotations

from pathlib import Path

from hypercharge.session import (
    active_open_chats,
    ensure_session_layout,
    peek_current_chat_id,
    register_new_chat,
    set_current_chat,
)
from hypercharge.ui.console import HyperConsole


def run_new_chat(
    root: Path,
    console: HyperConsole,
    *,
    goal: str,
    related_to: list[str] | None = None,
    resume: str | None = None,
) -> int:
    root = root.resolve()
    if not (root / ".cursor").is_dir():
        console.step_fail("New chat", "Run hypercharge setup in this repo first.")
        return 1

    ensure_session_layout(root)
    active = {c.get("id"): c for c in active_open_chats(root)}

    if resume:
        if resume not in active:
            console.step_fail("New chat", f"Unknown thread {resume} — not in OPEN_CHATS")
            return 1
        set_current_chat(root, resume)
        row = active[resume]
        print(f"chat_id: {resume}")
        print(f"goal: {row.get('goal', '—')}")
        print(f"resumed: yes")
        print(f"log: .cursor/session/chats/{resume}.md")
        return 0

    if not goal.strip():
        if active:
            print("Active threads (use --resume <id> or --goal \"…\"):")
            for cid, row in sorted(active.items()):
                print(f"  {cid}: {row.get('goal', '—')}")
        console.step_fail("New chat", 'Pass --goal "what this thread is for" or --resume <chat_id>')
        return 1

    cid = register_new_chat(root, goal=goal, related_to=related_to)
    print(f"chat_id: {cid}")
    print(f"goal: {goal.strip()}")
    if related_to:
        print(f"related_to: {', '.join(related_to)}")
    if active:
        print(f"other_threads: {len(active)}")
    print(f"log: .cursor/session/chats/{cid}.md")
    return 0
