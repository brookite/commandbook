"""Parse trusted connector configuration into argv without invoking a shell."""

from __future__ import annotations

import shlex
from collections.abc import Mapping
from pathlib import Path

from commandbook.config.models import Connector
from commandbook.connectors.models import (
    ConnectorError,
    ConnectorKind,
    ResolvedConnector,
    shell_from_name,
)

_TTY_FLAGS = frozenset({"-i", "-t", "-it", "-ti", "-T", "--interactive", "--tty"})
_OPTIONS_WITH_VALUE = frozenset(
    {
        "-e",
        "--env",
        "--env-file",
        "--detach-keys",
        "--index",
        "-u",
        "--user",
        "-w",
        "--workdir",
    }
)


def resolve_connector(
    value: str,
    configured: Mapping[str, Connector],
    *,
    persistent_override: bool = False,
) -> ResolvedConnector:
    """Resolve an exact alias first, otherwise parse ``value`` as a connector command."""
    selected = configured.get(value)
    if selected is None:
        return parse_connector_command(value, persistent=persistent_override)
    return parse_connector_command(
        selected.command,
        alias=selected.alias,
        persistent=selected.persistent or persistent_override,
        cwd=selected.cwd,
    )


def parse_connector_command(
    command: str,
    *,
    alias: str | None = None,
    persistent: bool = False,
    cwd: str | None = None,
) -> ResolvedConnector:
    """Recognize the supported connector command families."""
    try:
        argv = shlex.split(command, posix=True)
    except ValueError as exc:
        raise ConnectorError(f"Invalid connector command: {exc}") from exc
    if not argv:
        raise ConnectorError("Connector command must not be empty")

    executable = Path(argv[0]).name.lower()
    shell = shell_from_name(executable)
    if shell is not None:
        return ResolvedConnector(
            alias=alias,
            command=command,
            argv=tuple(argv),
            kind=ConnectorKind.SHELL,
            persistent=persistent,
            cwd=cwd,
            shell_hint=shell,
        )
    if executable == "ssh":
        return ResolvedConnector(
            alias=alias,
            command=command,
            argv=tuple(argv),
            kind=ConnectorKind.SSH,
            persistent=persistent,
            cwd=cwd,
        )
    if executable != "docker":
        raise ConnectorError(
            "Unsupported connector; expected a shell path, ssh, docker exec, or docker compose exec"
        )

    if len(argv) >= 2 and argv[1] == "exec":
        kind = ConnectorKind.DOCKER
        exec_index = 1
    elif len(argv) >= 3 and argv[1:3] == ["compose", "exec"]:
        kind = ConnectorKind.DOCKER_COMPOSE
        exec_index = 2
    else:
        raise ConnectorError("Docker connectors must use 'docker exec' or 'docker compose exec'")

    cleaned = argv[: exec_index + 1]
    tail = argv[exec_index + 1 :]
    target_index = _copy_options_and_find_target(tail, cleaned)
    if target_index is None:
        raise ConnectorError("Docker connector is missing a container or Compose service")
    remaining = tail[target_index + 1 :]
    shell_hint = shell_from_name(remaining[0]) if remaining else None
    if remaining and shell_hint is None:
        raise ConnectorError(
            "A Docker connector may only specify a supported shell after its target"
        )
    shell_index = len(cleaned) if remaining else None
    cleaned.extend(remaining)
    return ResolvedConnector(
        alias=alias,
        command=command,
        argv=tuple(cleaned),
        kind=kind,
        persistent=persistent,
        cwd=cwd,
        shell_hint=shell_hint,
        docker_exec_index=exec_index,
        docker_shell_index=shell_index,
    )


def _copy_options_and_find_target(tail: list[str], cleaned: list[str]) -> int | None:
    index = 0
    while index < len(tail):
        token = tail[index]
        if token in _TTY_FLAGS:
            index += 1
            continue
        if token == "--":
            index += 1
            if index >= len(tail):
                return None
            cleaned.append(tail[index])
            return index
        if token.startswith("-"):
            cleaned.append(token)
            if token in _OPTIONS_WITH_VALUE:
                index += 1
                if index >= len(tail):
                    raise ConnectorError(f"Docker option {token!r} requires a value")
                cleaned.append(tail[index])
            index += 1
            continue
        cleaned.append(token)
        return index
    return None


def docker_argv(
    connector: ResolvedConnector,
    shell_executable: str,
    *,
    interactive: bool,
) -> list[str]:
    """Build Docker argv with Commandbook-owned TTY flags and selected shell."""
    if connector.docker_exec_index is None:
        raise ConnectorError("Not a Docker connector")
    argv = list(connector.argv)
    if connector.docker_shell_index is not None:
        argv = argv[: connector.docker_shell_index]
    flag = "-it" if connector.kind is ConnectorKind.DOCKER else "--interactive"
    if interactive:
        argv.insert(connector.docker_exec_index + 1, flag)
    argv.append(shell_executable)
    return argv
