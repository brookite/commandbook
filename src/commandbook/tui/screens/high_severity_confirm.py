"""Confirmation shown immediately before a high-severity command runs."""

from __future__ import annotations

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from commandbook.commands.registry import CommandEntry


class HighSeverityConfirmScreen(ModalScreen[bool]):
    """Require an explicit confirmation for a potentially destructive command."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, entry: CommandEntry) -> None:
        super().__init__()
        self.entry = entry

    def compose(self) -> ComposeResult:
        command = self.entry.command
        with Vertical(id="high-severity-confirm"):
            yield Static("HIGH-RISK COMMAND", id="confirm-level")
            yield Static(escape(command.name), id="confirm-title")
            if command.description:
                yield Static(escape(command.description), id="confirm-description")
            yield Static(
                "Are you sure you want to run this command? "
                "It may make destructive or irreversible changes.",
                id="confirm-warning",
            )
            with Horizontal(id="confirm-buttons"):
                yield Button("Run anyway", id="confirm-run", variant="error")
                yield Button("Cancel", id="confirm-cancel", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#confirm-cancel", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-run")

    def action_cancel(self) -> None:
        self.dismiss(False)
