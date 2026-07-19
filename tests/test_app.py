"""Headless smoke tests for the Textual app."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Input, OptionList

from commandbook.tui import app as app_module
from commandbook.tui.app import CommandbookApp, default_config_path

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "commandbook.toml"


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
            app.action_back()
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


def test_app_reports_missing_config(tmp_path):
    async def scenario() -> None:
        missing = tmp_path / "nope.toml"
        app = CommandbookApp(config_path=missing)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.registry is None

    _run(scenario())
