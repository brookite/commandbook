"""Commandbook Textual application: fuzzy command list, form, and runner."""

from __future__ import annotations

import os
from pathlib import Path
from typing import cast

from rich.markup import escape
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Input, OptionList, Static
from textual.widgets.option_list import Option

from commandbook.commands.builder import RenderSpec, build_command
from commandbook.commands.registry import CommandEntry, CommandRegistry
from commandbook.config.loader import ConfigError, load_config
from commandbook.config.models import Group
from commandbook.shell.detect import ShellNotFoundError, detect_shell
from commandbook.shell.runner import resolve_cwd, run_command
from commandbook.tui.screens.high_severity_confirm import HighSeverityConfirmScreen
from commandbook.tui.screens.placeholder_form import PlaceholderFormScreen
from commandbook.variables.store import VariableStore

_DEFAULT_CONFIG_NAME = "commandbook.toml"


def default_config_paths() -> list[Path]:
    """Config locations searched when no ``--config`` is given, in priority order.

    A project-local file takes precedence over the one in the home directory.
    """
    return [Path.cwd() / _DEFAULT_CONFIG_NAME, Path.home() / _DEFAULT_CONFIG_NAME]


def default_config_path() -> Path | None:
    """Return the first existing default config location, or ``None``."""
    for candidate in default_config_paths():
        if candidate.is_file():
            return candidate
    return None


class _NavOptionList(OptionList):
    """OptionList that returns focus to the search box on ``Up`` at the top."""

    def action_cursor_up(self) -> None:
        if self.highlighted in (0, None):
            cast("CommandbookApp", self.app).action_focus_search()
        else:
            super().action_cursor_up()


def _format_entry(entry: CommandEntry, *, show_group: bool = False) -> str:
    """Render a command entry as a Rich-markup line for the option list."""
    line = escape(entry.command.name)
    if show_group:
        line += f"  [dim]· {escape(entry.group.name)}[/dim]"
    elif entry.command.description:
        line += f"  [dim]{escape(entry.command.description)}[/dim]"
    if entry.command.tags:
        tags = " ".join(f"#{escape(tag)}" for tag in entry.command.tags)
        line += f"  [dim cyan]{tags}[/dim cyan]"
    return line


def _format_group(group: Group, count: int) -> str:
    """Render a group as a Rich-markup line for the option list."""
    line = f"{escape(group.name)}  [dim]({count})[/dim]"
    if group.description:
        line += f"  [dim]{escape(group.description)}[/dim]"
    if group.tags:
        tags = " ".join(f"#{escape(tag)}" for tag in group.tags)
        line += f"  [dim cyan]{tags}[/dim cyan]"
    return line


class CommandbookApp(App[None]):
    """Root application: search commands, fill placeholders, run."""

    TITLE = "Commandbook"
    CSS = """
    #breadcrumb { dock: top; margin: 0 1; color: $text-muted; }
    #search { dock: top; margin: 0 1; }
    #commands { height: 1fr; margin: 0 1; }
    #status { dock: bottom; color: $error; padding: 0 1; }
    PlaceholderFormScreen { align: center middle; }
    #form { width: 70%; max-width: 90; height: auto; max-height: 80%;
            border: thick $primary; background: $surface; padding: 1 2; }
    #form-title { text-style: bold; }
    #form-tags { height: auto; padding-top: 1; }
    #form-description { height: auto; color: $text-muted; padding: 0 0 1 0; }
    #form-buttons { height: auto; padding-top: 1; }
    #form-buttons Button { margin-right: 2; }
    .hint { color: $text-muted; }
    .warn { color: $warning; }
    HighSeverityConfirmScreen { align: center middle; }
    #high-severity-confirm { width: 64; height: auto; border: thick $error;
                             background: $surface; padding: 1 2; }
    #confirm-level { color: $error; text-style: bold; }
    #confirm-title { height: auto; text-style: bold; padding-top: 1; }
    #confirm-description { height: auto; color: $text-muted; }
    #confirm-warning { height: auto; padding: 1 0; }
    #confirm-buttons { height: auto; }
    #confirm-buttons Button { margin-right: 2; }
    """
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+f", "focus_search", "Search"),
        Binding("slash", "focus_search", "Search", show=False),
        Binding("ctrl+g", "toggle_groups", "Groups"),
        Binding("escape", "navigate_back", "Back"),
    ]

    def __init__(self, config_path: Path | None = None) -> None:
        super().__init__()
        self.config_path = config_path
        self.registry: CommandRegistry | None = None
        self.store: VariableStore | None = None
        self._shell_pref = "auto"
        self._level = "all"  # "all" | "groups" | "commands"
        self._current_group: Group | None = None
        self._visible_groups: list[Group] = []
        self._visible: list[CommandEntry] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("All commands", id="breadcrumb")
        yield Input(placeholder="Search commands…", id="search")
        yield _NavOptionList(id="commands")
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        path = self.config_path or default_config_path()
        if path is None:
            self._fail(
                f"No config found. Pass --config, or add {_DEFAULT_CONFIG_NAME} to the "
                f"current directory or your home directory (~/{_DEFAULT_CONFIG_NAME})."
            )
            return
        try:
            config = load_config(path)
        except ConfigError as exc:
            self._fail(str(exc))
            return
        self.registry = CommandRegistry(config)
        self.store = VariableStore(config.variable_groups)
        self._shell_pref = config.settings.shell
        self._enter_all()

    # --- Navigation: all-commands (main) <-> groups -> a group's commands ----

    def _enter_all(self) -> None:
        """Main view: the flat list of every command."""
        self._level = "all"
        self._current_group = None
        self.query_one("#breadcrumb", Static).update("All commands")
        self.query_one("#search", Input).placeholder = "Search commands…"
        self._reset_search()
        self.apply_query("")

    def _enter_groups(self) -> None:
        """Groups view (toggled with Ctrl+G): the list of groups."""
        self._level = "groups"
        self._current_group = None
        self.query_one("#breadcrumb", Static).update("Groups  [dim](Ctrl+G: all commands)[/dim]")
        self.query_one("#search", Input).placeholder = "Search groups…"
        self._reset_search()
        self.apply_query("")

    def _enter_group(self, group: Group) -> None:
        """Drill into ``group`` and show its commands."""
        self._level = "commands"
        self._current_group = group
        self.query_one("#breadcrumb", Static).update(f"Groups › {escape(group.name)}")
        self.query_one("#search", Input).placeholder = f"Search commands in {group.name}…"
        self._reset_search()
        self.apply_query("")
        self.query_one("#commands", OptionList).focus()

    def _reset_search(self) -> None:
        search = self.query_one("#search", Input)
        with search.prevent(Input.Changed):
            search.value = ""

    def apply_query(self, query: str) -> None:
        """Repopulate the list for the current level, filtered by ``query``."""
        if self.registry is None:
            return
        option_list = self.query_one("#commands", OptionList)
        option_list.clear_options()
        if self._level == "groups":
            self._visible_groups = self.registry.search_groups(query)
            option_list.add_options(
                Option(_format_group(group, len(self.registry.entries_in(group))), id=str(index))
                for index, group in enumerate(self._visible_groups)
            )
            return

        if self._level == "commands":
            assert self._current_group is not None
            self._visible = self.registry.search_commands_in(self._current_group, query)
            show_group = False
        else:  # "all"
            self._visible = self.registry.search(query)
            show_group = True
        option_list.add_options(
            Option(_format_entry(entry, show_group=show_group), id=str(index))
            for index, entry in enumerate(self._visible)
        )

    def on_key(self, event: events.Key) -> None:
        # Down arrow in the search box moves into the results list.
        if event.key != "down":
            return
        if self.focused is not self.query_one("#search", Input):
            return
        option_list = self.query_one("#commands", OptionList)
        if option_list.option_count:
            option_list.focus()
            option_list.highlighted = 0
            event.stop()
            event.prevent_default()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search":
            self.apply_query(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "search":
            return
        if self._level == "groups" and self._visible_groups:
            self._enter_group(self._visible_groups[0])
        elif self._level in ("all", "commands") and self._visible:
            self._launch(self._visible[0])

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id is None:
            return
        index = int(event.option_id)
        if self._level == "groups":
            self._enter_group(self._visible_groups[index])
        else:
            self._launch(self._visible[index])

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_toggle_groups(self) -> None:
        """Ctrl+G: switch between the all-commands view and the groups view."""
        if self.registry is None:
            return
        if self._level == "all":
            self._enter_groups()
        else:
            self._enter_all()

    def action_navigate_back(self) -> None:
        """Esc: from search go to the list; from a group's commands go back up."""
        search = self.query_one("#search", Input)
        option_list = self.query_one("#commands", OptionList)
        if self.focused is search:
            option_list.focus()
        elif self._level == "commands":
            self._enter_groups()
            option_list.focus()

    def _launch(self, entry: CommandEntry) -> None:
        if entry.command.placeholders:
            self.push_screen(
                PlaceholderFormScreen(entry, presets=self._presets_for(entry)),
                lambda values: self._confirm_or_run(entry, values) if values is not None else None,
            )
        else:
            self._confirm_or_run(entry, {})

    def _confirm_or_run(self, entry: CommandEntry, values: dict[str, str | bool]) -> None:
        if entry.command.severity == "high":
            self.push_screen(
                HighSeverityConfirmScreen(entry),
                lambda confirmed: self._run(entry, values) if confirmed else None,
            )
            return
        self._run(entry, values)

    def _presets_for(self, entry: CommandEntry) -> dict[str, list[str]]:
        """Preset values for placeholders that name a variable in the active group."""
        if self.store is None:
            return {}
        presets: dict[str, list[str]] = {}
        for placeholder in entry.command.placeholders:
            values = self.store.values_for(entry.group.variables, placeholder.name)
            if values:
                presets[placeholder.name] = values
        return presets

    def _run(self, entry: CommandEntry, values: dict[str, str | bool]) -> None:
        try:
            shell = detect_shell(self._shell_pref)
        except ShellNotFoundError as exc:
            self.notify(str(exc), severity="error")
            return

        template = entry.command.template_for(shell.name)
        specs = {
            placeholder.name: RenderSpec(
                escape=placeholder.escape,
                quote_style=placeholder.quote_style,
                strip_quotes=placeholder.strip_quotes,
            )
            for placeholder in entry.command.placeholders
        }
        command = build_command(
            template, values, quote_as=shell.quote_as, cwd=os.getcwd(), specs=specs
        )
        cwd = resolve_cwd(entry.command, entry.group, values)

        with self.suspend():
            print(f"$ {command}\n")
            code = run_command(shell, command, cwd=cwd)
            input("\n[Commandbook] Press Enter to return…")
        self.notify(f"Exited with code {code}")

    def _fail(self, message: str) -> None:
        self.query_one("#status", Static).update(message)
        self.notify(message, severity="error", timeout=10)
