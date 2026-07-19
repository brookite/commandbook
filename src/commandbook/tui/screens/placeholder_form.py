"""Modal screen that collects and validates a command's placeholder values."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label, Select, Static

from commandbook.placeholders.types import ValidationError, validate_value

if TYPE_CHECKING:
    from collections.abc import Mapping

    from commandbook.commands.registry import CommandEntry
    from commandbook.config.models import Placeholder

Values = dict[str, str | bool]
Field = Input | Checkbox | Select


class PlaceholderFormScreen(ModalScreen[Values | None]):
    """Ask for every placeholder of a command; dismiss with normalized values.

    Dismisses with ``None`` when cancelled.
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(
        self,
        entry: CommandEntry,
        presets: Mapping[str, list[str]] | None = None,
    ) -> None:
        super().__init__()
        self.entry = entry
        self.presets: Mapping[str, list[str]] = presets or {}
        self._inputs: dict[str, Field] = {}

    def compose(self) -> ComposeResult:
        command = self.entry.command
        with VerticalScroll(id="form"):
            yield Static(f"[b]{command.name}[/b]", id="form-title")
            for placeholder in command.placeholders:
                yield from self._compose_field(placeholder)
            yield Static("", id="form-error")
            with Horizontal(id="form-buttons"):
                yield Button("Run", id="run", variant="primary")
                yield Button("Cancel", id="cancel")

    def _compose_field(self, placeholder: Placeholder) -> ComposeResult:
        label = placeholder.label or placeholder.name
        suffix = "" if placeholder.optional else " *"

        if placeholder.type == "checkbox":
            checkbox = Checkbox(f"{label}{suffix}", value=self._checkbox_default(placeholder))
            self._inputs[placeholder.name] = checkbox
            yield checkbox
            yield from self._field_hints(placeholder)
            return

        yield Label(f"{label}{suffix}  ({placeholder.type})")
        yield from self._field_hints(placeholder)

        options = self.presets.get(placeholder.name)
        if options:
            self._inputs[placeholder.name] = self._make_select(placeholder, options)
        else:
            self._inputs[placeholder.name] = Input(
                value=placeholder.default or "", placeholder=placeholder.description
            )
        yield self._inputs[placeholder.name]

    def _make_select(self, placeholder: Placeholder, options: list[str]) -> Select:
        choices = [(value, value) for value in options]
        default = placeholder.default if placeholder.default in options else None
        return Select(
            choices,
            value=default if default is not None else Select.BLANK,
            allow_blank=placeholder.optional or default is None,
            prompt="Choose a preset…",
        )

    def _field_hints(self, placeholder: Placeholder) -> ComposeResult:
        if placeholder.description:
            yield Label(placeholder.description, classes="hint")
        if placeholder.strip_quotes:
            yield Label("Note: surrounding quotes you type here will be removed.", classes="warn")

    @staticmethod
    def _checkbox_default(placeholder: Placeholder) -> bool:
        if not placeholder.default:
            return False
        try:
            return bool(validate_value("checkbox", placeholder.default))
        except ValidationError:
            return False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run":
            self._submit()
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Pressing Enter in any field submits the whole form.
        self._submit()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _submit(self) -> None:
        search_dirs = self.entry.group.search_dirs
        values: Values = {}
        for placeholder in self.entry.command.placeholders:
            widget = self._inputs[placeholder.name]
            if isinstance(widget, Checkbox):
                values[placeholder.name] = widget.value
                continue

            raw = self._raw_value(widget)
            if not raw:
                if placeholder.optional:
                    values[placeholder.name] = ""
                    continue
                self._show_error(f"{placeholder.label or placeholder.name}: required")
                return
            try:
                values[placeholder.name] = validate_value(
                    placeholder.type, raw, pattern=placeholder.pattern, search_dirs=search_dirs
                )
            except ValidationError as exc:
                self._show_error(f"{placeholder.label or placeholder.name}: {exc}")
                return
        self.dismiss(values)

    @staticmethod
    def _raw_value(widget: Field) -> str:
        if isinstance(widget, Select):
            return "" if widget.value is Select.BLANK else str(widget.value)
        return widget.value.strip()

    def _show_error(self, message: str) -> None:
        self.query_one("#form-error", Static).update(f"[red]{message}[/red]")
