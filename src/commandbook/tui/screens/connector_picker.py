"""Modal used to select a configured or custom command connector."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Select, Static

from commandbook.config.models import Connector


@dataclass(frozen=True, slots=True)
class ConnectorRequest:
    """User selection returned by :class:`ConnectorPickerScreen`."""

    value: str | None
    persistent: bool = False
    resolve_alias: bool = True


class ConnectorPickerScreen(ModalScreen[ConnectorRequest | None]):
    """Choose Local, a configured alias, or an arbitrary connector command."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, connectors: Mapping[str, Connector]) -> None:
        super().__init__()
        self.connectors = connectors

    def compose(self) -> ComposeResult:
        choices = [("Local shell", "__local__")]
        choices.extend((alias, alias) for alias in self.connectors)
        choices.append(("Custom command…", "__custom__"))
        with Vertical(id="connector-picker"):
            yield Static("Connect shell", id="connector-title")
            yield Static(
                "Choose a configured alias or enter a shell, SSH, or Docker command.",
                id="connector-description",
            )
            yield Select(choices, value="__local__", allow_blank=False, id="connector-choice")
            yield Input(
                placeholder="ssh production | docker compose exec api | /usr/bin/bash",
                id="connector-command",
                disabled=True,
            )
            yield Checkbox("Persistent connection", id="connector-persistent", disabled=True)
            yield Static("", id="connector-error")
            with Horizontal(id="connector-buttons"):
                yield Button("Select", id="connector-select", variant="primary")
                yield Button("Cancel", id="connector-cancel")

    def on_select_changed(self, event: Select.Changed) -> None:
        custom = event.value == "__custom__"
        self.query_one("#connector-command", Input).disabled = not custom
        self.query_one("#connector-persistent", Checkbox).disabled = not custom
        if custom:
            self.query_one("#connector-command", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "connector-cancel":
            self.dismiss(None)
            return
        self._submit()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def _submit(self) -> None:
        value = self.query_one("#connector-choice", Select).value
        if value == "__local__":
            self.dismiss(ConnectorRequest(None))
            return
        if value == "__custom__":
            command = self.query_one("#connector-command", Input).value.strip()
            if not command:
                self.query_one("#connector-error", Static).update(
                    "[red]Enter a connector command.[/red]"
                )
                return
            persistent = self.query_one("#connector-persistent", Checkbox).value
            self.dismiss(ConnectorRequest(command, persistent=persistent, resolve_alias=False))
            return
        self.dismiss(ConnectorRequest(str(value)))

    def action_cancel(self) -> None:
        self.dismiss(None)
