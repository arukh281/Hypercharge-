"""Rich terminal UI for Hypercharge."""

from __future__ import annotations

import os
import sys
from typing import Iterable

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from hypercharge import __version__
from hypercharge.ui import copy_en_gb as copy


class HyperConsole:
    def __init__(self, plain: bool | None = None) -> None:
        """Internal __init__. Args: plain. (hypercharge-managed)"""
        if plain is None:
            plain = bool(os.environ.get("NO_COLOR")) or not sys.stdout.isatty()
        self.plain = plain
        self.console = Console(force_terminal=not plain, highlight=not plain)

    def banner(self) -> None:
        """Banner. (hypercharge-managed)"""
        if self.plain:
            print(f"{copy.APP_TITLE} v{__version__} — {copy.APP_TAGLINE}")
            return
        self.console.print(
            Panel(
                f"[bold]{copy.APP_TITLE}[/] · v{__version__} · en-GB\n[dim]{copy.APP_TAGLINE}[/]",
                border_style="cyan",
                expand=False,
            )
        )

    def step_ok(self, label: str, step: int, total: int) -> None:
        """Step ok. Args: label, step, total. (hypercharge-managed)"""
        line = f"[{step}/{total}] {label} ... ok"
        if self.plain:
            print(line)
        else:
            self.console.print(f"  [green]✓[/] [{step}/{total}] {label}")

    def step_fail(self, label: str, message: str) -> None:
        """Step fail. Args: label, message. (hypercharge-managed)"""
        if self.plain:
            print(f"FAIL {label}: {message}")
        else:
            self.console.print(Panel(f"[bold red]{label}[/]\n{message}", border_style="red"))

    def footer(self, title: str, lines: Iterable[str]) -> None:
        """Footer. Args: title, lines. (hypercharge-managed)"""
        body = "\n".join(lines)
        if self.plain:
            print(f"\n{title}\n{body}")
            return
        self.console.print(Panel(body, title=f"[bold green]{title}[/]", border_style="green"))

    def warn(self, message: str) -> None:
        """Warn. Args: message. (hypercharge-managed)"""
        if self.plain:
            print(f"WARNING: {message}")
        else:
            self.console.print(Panel(message, title="[yellow]Notice[/]", border_style="yellow"))

    def health_table(self, rows: list[tuple[str, str, str]]) -> None:
        """Health table. Args: rows. (hypercharge-managed)"""
        if self.plain:
            for name, status, detail in rows:
                print(f"  {name}: {status} — {detail}")
            return
        table = Table(title="Health", show_header=True, header_style="bold")
        table.add_column("Check")
        table.add_column("Status")
        table.add_column("Detail")
        for name, status, detail in rows:
            colour = "green" if status == "ok" else ("yellow" if status == "warn" else "red")
            table.add_row(name, Text(status, style=colour), detail)
        self.console.print(table)

    def inventory_table(self, rows: list[dict[str, str]]) -> None:
        """Inventory table. Args: rows. (hypercharge-managed)"""
        if self.plain:
            for r in rows:
                print(f"  [{r.get('type', '?')}] {r.get('name', '?')} → {r.get('recommendation', '?')}")
            return
        table = Table(title="Rules & skills inventory", show_header=True, header_style="bold")
        table.add_column("Name")
        table.add_column("Type")
        table.add_column("Recommendation")
        table.add_column("Reason")
        for r in rows:
            table.add_row(
                r.get("name", ""),
                r.get("type", ""),
                r.get("recommendation", ""),
                r.get("reason", ""),
            )
        self.console.print(table)

    def wrapup_chat_panel(
        self,
        chat_id: str,
        archived: bool,
        open_questions: int,
        experiment: bool,
    ) -> None:
        """Wrapup chat panel. Args: chat_id, archived, open_questions, experiment. (hypercharge-managed)"""
        status = "archived" if archived else "active"
        lines = [
            f"Chat: {chat_id}",
            f"Status: {status}",
            f"Open questions: {open_questions}",
        ]
        if experiment:
            lines.append("Promotions held — use day wrapup when stable.")
        title = "Chat wrapped"
        self.footer(title, lines)

    def wrapup_day_panel(
        self,
        chats_today: int,
        graph_updated: bool,
        held_back: list[str],
    ) -> None:
        """Wrapup day panel. Args: chats_today, graph_updated, held_back. (hypercharge-managed)"""
        lines = [
            f"Chats consolidated today: {chats_today}",
            f"Graph updated: {'yes' if graph_updated else 'no'}",
        ]
        if held_back:
            lines.append("Held back: " + ", ".join(held_back))
        self.footer("Day wrapup complete", lines)

    def spinner(self, message: str):
        """Spinner. Args: message. Returns: Progress(SpinnerColumn(), TextColumn('[progress.de. (hypercharge-managed)"""
        if self.plain:
            print(message + "...")
            from contextlib import contextmanager

            @contextmanager
            def _noop():
                """Internal _noop. (hypercharge-managed)"""
                yield

            return _noop()
        return Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
            transient=True,
        )
