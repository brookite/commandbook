"""Connector command parsing, shell detection, and POSIX PTY lifecycle tests."""

from __future__ import annotations

import os
import shutil

import pytest

from commandbook.config.models import Connector
from commandbook.connectors.detector import shell_from_probe
from commandbook.connectors.manager import ConnectionManager
from commandbook.connectors.models import ConnectorError, ConnectorKind
from commandbook.connectors.parser import docker_argv, parse_connector_command, resolve_connector


def test_alias_resolution_and_persistent_override():
    configured = {"prod": Connector(alias="prod", command="ssh deploy@example", persistent=False)}
    connector = resolve_connector("prod", configured, persistent_override=True)

    assert connector.alias == "prod"
    assert connector.kind is ConnectorKind.SSH
    assert connector.persistent is True
    assert connector.argv == ("ssh", "deploy@example")


def test_direct_shell_detection_from_path():
    connector = parse_connector_command("/usr/bin/bash --noprofile")
    assert connector.kind is ConnectorKind.SHELL
    assert connector.shell_hint is not None
    assert connector.shell_hint.name == "bash"


def test_docker_exec_normalizes_tty_and_accepts_optional_shell():
    connector = parse_connector_command("docker exec -it -u app backend")
    assert connector.argv == ("docker", "exec", "-u", "app", "backend")
    assert docker_argv(connector, "bash", interactive=True) == [
        "docker",
        "exec",
        "-it",
        "-u",
        "app",
        "backend",
        "bash",
    ]

    compose = parse_connector_command("docker compose exec -T api /bin/sh")
    assert compose.kind is ConnectorKind.DOCKER_COMPOSE
    assert compose.shell_hint is not None and compose.shell_hint.name == "sh"
    assert docker_argv(compose, "/bin/sh", interactive=True) == [
        "docker",
        "compose",
        "exec",
        "--interactive",
        "api",
        "/bin/sh",
    ]


@pytest.mark.parametrize("command", ["", "curl host", "docker run image", "docker exec"])
def test_unsupported_connector_commands_raise(command):
    with pytest.raises(ConnectorError):
        parse_connector_command(command)


def test_probe_shell_normalization():
    assert shell_from_probe("-bash").name == "bash"
    assert shell_from_probe("/bin/zsh").dialect == "posix"
    assert shell_from_probe("unknown") is None


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="POSIX bash required")
def test_persistent_session_preserves_shell_state(capfd):
    connector = parse_connector_command(shutil.which("bash") or "bash", persistent=True)
    manager = ConnectionManager()
    manager.select(connector)
    try:
        shell = manager.prepare()
        assert shell.name == "bash"
        assert manager.run("export COMMANDBOOK_TEST_STATE=kept") == 0
        assert manager.run('printf %s "$COMMANDBOOK_TEST_STATE"') == 0
        assert manager.run("cd /tmp") == 0
        assert manager.run('test "$PWD" = /tmp') == 0
        assert manager.run('test "$PWD" = /', cwd="/") == 0
        assert manager.run('test "$PWD" = /tmp') == 0
        assert manager.run("true;") == 0
    finally:
        manager.disconnect()

    assert "kept" in capfd.readouterr().out


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="POSIX bash required")
def test_ephemeral_session_clears_selection():
    connector = parse_connector_command(shutil.which("bash") or "bash", persistent=False)
    manager = ConnectionManager()
    manager.select(connector)
    assert manager.run("true") == 0
    assert manager.connector is None
