"""Domain types shared by connector implementations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from commandbook.shell.detect import BASH_QUOTERS, POWERSHELL_QUOTERS, Quoter


class ConnectorError(RuntimeError):
    """A connector could not be parsed, opened, detected, or used."""


class ConnectorKind(StrEnum):
    SHELL = "shell"
    SSH = "ssh"
    DOCKER = "docker"
    DOCKER_COMPOSE = "docker-compose"


@dataclass(frozen=True, slots=True)
class DetectedShell:
    """Concrete shell name plus the command/quoting dialect it implements."""

    name: str
    dialect: str
    quoters: dict[str, Quoter]
    executable: str

    def quote_as(self, style: str, value: str) -> str:
        quoter = self.quoters.get(style) or self.quoters["auto"]
        return quoter(value)


POSIX_SHELLS = frozenset({"bash", "sh", "dash", "zsh", "ksh"})
POWERSHELL_NAMES = frozenset({"pwsh", "powershell", "powershell.exe", "pwsh.exe"})


def shell_from_name(name: str) -> DetectedShell | None:
    """Map an executable/process name to a supported shell dialect."""
    normalized = Path(name.strip()).name.lower().lstrip("-")
    if normalized in POSIX_SHELLS:
        return DetectedShell(
            name=normalized, dialect="posix", quoters=BASH_QUOTERS, executable=name.strip()
        )
    if normalized in POWERSHELL_NAMES:
        return DetectedShell(
            name="powershell",
            dialect="powershell",
            quoters=POWERSHELL_QUOTERS,
            executable=name.strip(),
        )
    return None


@dataclass(frozen=True, slots=True)
class ResolvedConnector:
    """Validated connector command with inferred transport metadata."""

    alias: str | None
    command: str
    argv: tuple[str, ...]
    kind: ConnectorKind
    persistent: bool
    cwd: str | None = None
    shell_hint: DetectedShell | None = None
    docker_exec_index: int | None = None
    docker_shell_index: int | None = None

    @property
    def display_name(self) -> str:
        return self.alias or self._safe_target()

    def _safe_target(self) -> str:
        if self.kind is ConnectorKind.SHELL:
            return Path(self.argv[0]).name
        if self.kind is ConnectorKind.SSH:
            return "ssh"
        if self.kind is ConnectorKind.DOCKER_COMPOSE:
            return "docker compose"
        return "docker"
