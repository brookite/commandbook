"""Headless smoke tests for the Textual app."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Button, Input, OptionList, Static

from commandbook.tui import app as app_module
from commandbook.tui.app import CommandbookApp, default_config_path
from commandbook.tui.screens.connector_picker import ConnectorPickerScreen, ConnectorRequest
from commandbook.tui.screens.high_severity_confirm import HighSeverityConfirmScreen
from commandbook.tui.screens.placeholder_form import PlaceholderFormScreen

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "commandbook.yaml"


def _run(coro) -> None:
    asyncio.run(coro)


def test_default_config_prefers_cwd_then_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()
    monkeypatch.setattr(app_module.Path, "home", classmethod(lambda cls: home))
    monkeypatch.chdir(cwd)

    assert default_config_path() is None

    (home / "commandbook.toml").write_text("", encoding="utf-8")
    assert default_config_path() == home / "commandbook.toml"

    (cwd / "commandbook.toml").write_text("", encoding="utf-8")
    assert default_config_path() == cwd / "commandbook.toml"

    (cwd / "commandbook.yaml").write_text("", encoding="utf-8")
    assert default_config_path() == cwd / "commandbook.yaml"


def test_app_main_view_lists_all_commands():
    async def scenario() -> None:
        app = CommandbookApp(config_path=EXAMPLE)
        async with app.run_test() as pilot:
            options = app.query_one("#commands", OptionList)
            # Main view shows every command.
            assert app._level == "all"
            assert options.option_count == 3

            app.apply_query("docker")
            await pilot.pause()
            assert options.option_count == 1

            app.apply_query("")
            await pilot.pause()
            assert options.option_count == 3

    _run(scenario())


def test_app_toggle_groups_and_drill_and_back():
    async def scenario() -> None:
        app = CommandbookApp(config_path=EXAMPLE)
        async with app.run_test() as pilot:
            options = app.query_one("#commands", OptionList)

            # Ctrl+G switches from all-commands to the groups view.
            app.action_toggle_groups()
            await pilot.pause()
            assert app._level == "groups"
            assert options.option_count == 3  # Docker, AWS, Git

            # Enter a group -> its commands.
            docker = next(g for g in app.registry.groups() if g.name == "Docker")
            app._enter_group(docker)
            await pilot.pause()
            assert app._level == "commands"
            assert [e.command.id for e in app._visible] == ["docker-build"]

            # Esc from the list goes back to the groups view.
            app.action_navigate_back()
            await pilot.pause()
            assert app._level == "groups"

            # Ctrl+G from groups returns to the all-commands view.
            app.action_toggle_groups()
            await pilot.pause()
            assert app._level == "all"
            assert options.option_count == 3

    _run(scenario())


def test_arrow_keys_move_between_search_and_list():
    async def scenario() -> None:
        app = CommandbookApp(config_path=EXAMPLE)
        async with app.run_test() as pilot:
            search = app.query_one("#search", Input)
            options = app.query_one("#commands", OptionList)

            search.focus()
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()
            assert app.focused is options

            # Up at the top item returns focus to the search box.
            options.highlighted = 0
            await pilot.press("up")
            await pilot.pause()
            assert app.focused is search

    _run(scenario())


def test_app_computes_presets_for_variable_placeholder():
    async def scenario() -> None:
        app = CommandbookApp(config_path=EXAMPLE)
        async with app.run_test():
            entry = next(e for e in app.registry.all() if e.command.id == "aws-ec2-list")
            assert app._presets_for(entry) == {"region": ["us-east-1", "eu-west-1"]}

    _run(scenario())


def test_ctrl_s_opens_connector_picker_and_ephemeral_alias_is_next_command_only():
    async def scenario() -> None:
        app = CommandbookApp(config_path=EXAMPLE)
        async with app.run_test() as pilot:
            app.action_select_connector()
            await pilot.pause()
            assert isinstance(app.screen, ConnectorPickerScreen)
            app.screen.dismiss(None)
            await pilot.pause()

            app._apply_connector_request(ConnectorRequest("postgres-container"))
            await pilot.pause()
            connector = app.connection.connector
            assert connector is not None
            assert connector.alias == "postgres-container"
            assert connector.persistent is False
            assert "Next command via postgres-container" in str(
                app.query_one("#connection-status", Static).content
            )

            app.action_disconnect()
            assert app.connection.connector is None
            assert str(app.query_one("#connection-status", Static).content) == "Local shell"

    _run(scenario())


def test_remote_form_does_not_validate_paths_on_local_filesystem():
    async def scenario() -> None:
        app = CommandbookApp(config_path=EXAMPLE)
        captured: list[dict[str, str | bool]] = []
        async with app.run_test() as pilot:
            entry = next(e for e in app.registry.all() if e.command.id == "docker-build")
            screen = PlaceholderFormScreen(entry, remote_paths=True)
            app.push_screen(screen, lambda values: captured.append(values or {}))
            await pilot.pause()
            screen._inputs["tag"].value = "demo"
            screen._inputs["dockerfile"].value = "/remote/Dockerfile"
            screen._inputs["context"].value = "/remote/context"
            screen._submit()
            await pilot.pause()

        assert captured == [
            {
                "tag": "demo",
                "dockerfile": "/remote/Dockerfile",
                "context": "/remote/context",
            }
        ]

    _run(scenario())


def test_form_shows_command_metadata_and_supports_arrow_navigation():
    async def scenario() -> None:
        app = CommandbookApp(config_path=EXAMPLE)
        async with app.run_test() as pilot:
            entry = next(e for e in app.registry.all() if e.command.id == "docker-build")
            app._launch(entry)
            await pilot.pause()

            screen = app.screen
            assert isinstance(screen, PlaceholderFormScreen)
            assert str(screen.query_one("#form-title", Static).content) == "Build image"
            assert "#build" in str(screen.query_one("#form-tags", Static).content)
            assert "Build a Docker image" in str(
                screen.query_one("#form-description", Static).content
            )

            tag = screen._inputs["tag"]
            dockerfile = screen._inputs["dockerfile"]
            tag.focus()
            await pilot.press("down")
            await pilot.pause()
            assert app.focused is dockerfile
            await pilot.press("up")
            await pilot.pause()
            assert app.focused is tag

    _run(scenario())


def test_high_severity_command_requires_confirmation(monkeypatch):
    async def scenario() -> None:
        app = CommandbookApp(config_path=EXAMPLE)
        calls: list[tuple[object, dict[str, str | bool]]] = []
        monkeypatch.setattr(app, "_run", lambda entry, values: calls.append((entry, values)))

        async with app.run_test() as pilot:
            entry = app.registry.all()[0]
            entry.command.severity = "high"
            app._confirm_or_run(entry, {"tag": "demo"})
            await pilot.pause()

            assert isinstance(app.screen, HighSeverityConfirmScreen)
            assert app.focused is app.screen.query_one("#confirm-cancel", Button)
            assert not calls

            await pilot.click("#confirm-run")
            await pilot.pause()
            assert calls == [(entry, {"tag": "demo"})]

    _run(scenario())


def test_app_reports_missing_config(tmp_path):
    async def scenario() -> None:
        missing = tmp_path / "nope.toml"
        app = CommandbookApp(config_path=missing)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.registry is None

    _run(scenario())
