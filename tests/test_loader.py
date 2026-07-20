"""Tests for the config loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from commandbook.config.loader import ConfigError, load_config, parse_config

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "commandbook.toml"


def test_load_example_config():
    config = load_config(EXAMPLE)
    assert config.settings.shell == "auto"
    assert [g.name for g in config.groups] == ["Docker", "AWS", "Git"]
    assert "aws" in config.variable_groups
    assert config.variable_groups["aws"].values["region"] == ["us-east-1", "eu-west-1"]

    commands = {cmd.id: cmd for _, cmd in config.iter_commands()}
    assert set(commands) == {"docker-build", "aws-ec2-list", "git-log"}

    build = commands["docker-build"]
    df = build.placeholder("dockerfile")
    assert df is not None and df.optional and df.type == "file"
    assert build.tags == ["build", "image"]
    assert build.description == "Build a Docker image from a context directory"
    assert config.groups[0].tags == ["containers", "devops"]

    filters = commands["aws-ec2-list"].placeholder("filters")
    assert filters is not None and filters.type == "bare" and filters.escape is False


def test_tags_must_be_an_array():
    data = {
        "groups": [
            {
                "name": "G",
                "tags": "not-a-list",
                "commands": [{"id": "c", "name": "C", "template": "x"}],
            }
        ]
    }
    with pytest.raises(ConfigError, match="tags"):
        parse_config(data)


def test_command_severity_defaults_to_none_and_accepts_known_levels():
    default = parse_config(_single_command({"id": "default", "name": "Default", "template": "x"}))
    high = parse_config(
        _single_command({"id": "danger", "name": "Danger", "template": "x", "severity": "high"})
    )

    assert default.groups[0].commands[0].severity == "none"
    assert high.groups[0].commands[0].severity == "high"


def test_unknown_command_severity_raises():
    data = _single_command(
        {"id": "danger", "name": "Danger", "template": "x", "severity": "critical"}
    )
    with pytest.raises(ConfigError, match="severity"):
        parse_config(data)


def test_template_for_falls_back():
    data = {
        "groups": [
            {
                "name": "G",
                "commands": [
                    {"id": "c1", "name": "C1", "shells": {"default": "echo d", "bash": "echo b"}}
                ],
            }
        ]
    }
    cmd = parse_config(data).groups[0].commands[0]
    assert cmd.template_for("bash") == "echo b"
    assert cmd.template_for("powershell") == "echo d"


def test_missing_group_name():
    with pytest.raises(ConfigError, match="name"):
        parse_config({"groups": [{"commands": []}]})


def test_missing_command_template():
    data = {"groups": [{"name": "G", "commands": [{"id": "c", "name": "C"}]}]}
    with pytest.raises(ConfigError, match="template"):
        parse_config(data)


def test_duplicate_command_id():
    data = {
        "groups": [
            {
                "name": "G",
                "commands": [
                    {"id": "dup", "name": "A", "template": "a"},
                    {"id": "dup", "name": "B", "template": "b"},
                ],
            }
        ]
    }
    with pytest.raises(ConfigError, match="Duplicate command id"):
        parse_config(data)


def test_bad_shell_setting():
    with pytest.raises(ConfigError, match="shell"):
        parse_config({"settings": {"shell": "fish"}})


def test_unknown_placeholder_type():
    data = {
        "groups": [
            {
                "name": "G",
                "commands": [
                    {
                        "id": "c",
                        "name": "C",
                        "template": "x",
                        "placeholders": [{"name": "p", "type": "uuid"}],
                    }
                ],
            }
        ]
    }
    with pytest.raises(ConfigError, match="unknown type"):
        parse_config(data)


def test_regex_placeholder_needs_pattern():
    data = {
        "groups": [
            {
                "name": "G",
                "commands": [
                    {
                        "id": "c",
                        "name": "C",
                        "template": "x",
                        "placeholders": [{"name": "p", "type": "regex"}],
                    }
                ],
            }
        ]
    }
    with pytest.raises(ConfigError, match="pattern"):
        parse_config(data)


def test_checkbox_forced_optional():
    data = {
        "groups": [
            {
                "name": "G",
                "commands": [
                    {
                        "id": "c",
                        "name": "C",
                        "template": "x",
                        "placeholders": [{"name": "flag", "type": "checkbox", "optional": False}],
                    }
                ],
            }
        ]
    }
    cmd = parse_config(data).groups[0].commands[0]
    assert cmd.placeholder("flag").optional is True


def test_cwd_from_must_reference_path_placeholder():
    data = {
        "groups": [
            {
                "name": "G",
                "commands": [
                    {
                        "id": "c",
                        "name": "C",
                        "template": "x",
                        "cwd_from": "p",
                        "placeholders": [{"name": "p", "type": "string"}],
                    }
                ],
            }
        ]
    }
    with pytest.raises(ConfigError, match="file/directory"):
        parse_config(data)


def test_unknown_variable_group_reference():
    data = {"groups": [{"name": "G", "variables": "missing", "commands": []}]}
    with pytest.raises(ConfigError, match="unknown variable group"):
        parse_config(data)


def _single_command(command: dict) -> dict:
    return {"groups": [{"name": "G", "commands": [command]}]}


def test_bare_type_forces_no_escape():
    data = _single_command(
        {
            "id": "c",
            "name": "C",
            "template": "x ${p}",
            "placeholders": [{"name": "p", "type": "bare", "escape": True}],
        }
    )
    ph = parse_config(data).groups[0].commands[0].placeholder("p")
    assert ph.type == "bare" and ph.escape is False


def test_escape_and_quote_style_parsed():
    data = _single_command(
        {
            "id": "c",
            "name": "C",
            "template": "x ${p}",
            "placeholders": [
                {
                    "name": "p",
                    "type": "string",
                    "escape": False,
                    "strip_quotes": True,
                    "quote_style": "double",
                }
            ],
        }
    )
    ph = parse_config(data).groups[0].commands[0].placeholder("p")
    assert ph.escape is False and ph.strip_quotes is True and ph.quote_style == "double"


def test_invalid_quote_style_raises():
    data = _single_command(
        {
            "id": "c",
            "name": "C",
            "template": "x ${p}",
            "placeholders": [{"name": "p", "type": "string", "quote_style": "curly"}],
        }
    )
    with pytest.raises(ConfigError, match="quote_style"):
        parse_config(data)


def test_undeclared_placeholder_becomes_implicit_string():
    data = _single_command({"id": "c", "name": "C", "template": "echo ${name} to ${place}"})
    command = parse_config(data).groups[0].commands[0]
    implicit = {p.name: p for p in command.placeholders}
    assert set(implicit) == {"name", "place"}
    assert implicit["name"].type == "string" and implicit["name"].escape is True


def test_predefined_cwd_is_not_an_implicit_placeholder():
    data = _single_command({"id": "c", "name": "C", "template": "ls ${cwd}/${dir}"})
    command = parse_config(data).groups[0].commands[0]
    assert [p.name for p in command.placeholders] == ["dir"]
