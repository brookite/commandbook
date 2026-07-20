"""Detect the command language used on the connector's far side."""

from __future__ import annotations

import subprocess

from commandbook.connectors.models import (
    ConnectorError,
    ConnectorKind,
    DetectedShell,
    ResolvedConnector,
    shell_from_name,
)
from commandbook.connectors.parser import docker_argv

_DOCKER_CANDIDATES = ("bash", "zsh", "sh", "pwsh")


def hinted_or_docker_shell(connector: ResolvedConnector) -> DetectedShell | None:
    """Return a direct hint or probe a Docker target for a usable shell."""
    if connector.shell_hint is not None:
        return connector.shell_hint
    if connector.kind not in (ConnectorKind.DOCKER, ConnectorKind.DOCKER_COMPOSE):
        return None

    for executable in _DOCKER_CANDIDATES:
        detected = shell_from_name(executable)
        assert detected is not None
        argv = docker_argv(connector, executable, interactive=False)
        if detected.dialect == "powershell":
            argv.extend(("-NoProfile", "-Command", "exit 0"))
        else:
            argv.extend(("-c", "exit 0"))
        try:
            result = subprocess.run(  # noqa: S603 - validated argv, never a shell string
                argv,
                cwd=connector.cwd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0:
            return detected
    raise ConnectorError("No supported shell found inside the Docker target")


def shell_from_probe(value: str) -> DetectedShell | None:
    """Normalize `$0` / executable output from a live session probe."""
    stripped = value.strip()
    if not stripped or stripped == "$0":
        return None
    return shell_from_name(stripped.split()[0])
