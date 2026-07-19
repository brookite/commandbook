"""Shell auto-detection and per-shell command invocation.

Preference order for ``auto``: bash (Git Bash on Windows) -> PowerShell -> cmd.
Each :class:`Shell` knows how to build an argv for a command string and how to
quote a value in a given style (``auto`` | ``single`` | ``double``).
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from commandbook.commands.builder import backtick_escape

Quoter = Callable[[str], str]


class ShellNotFoundError(RuntimeError):
    """No usable shell executable could be found."""


# --- Per-shell quoting -------------------------------------------------------


def quote_powershell(value: str) -> str:
    """Single-quote a value for PowerShell (doubling embedded quotes)."""
    return "'" + value.replace("'", "''") + "'"


def quote_cmd(value: str) -> str:
    """Best-effort minimal quoting for cmd.exe (basic, per project scope)."""
    if value and not re.search(r'[\s"^&|<>()%]', value):
        return value
    return '"' + value.replace('"', '""') + '"'


def _bash_single(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def _bash_double(value: str) -> str:
    return '"' + re.sub(r"([$`\"\\])", r"\\\1", value) + '"'


def _powershell_double(value: str) -> str:
    return '"' + value.replace("`", "``").replace('"', '`"').replace("$", "`$") + '"'


def _cmd_double(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


BASH_QUOTERS: dict[str, Quoter] = {
    "auto": shlex.quote,
    "single": _bash_single,
    "double": _bash_double,
    "backtick": backtick_escape,
}
POWERSHELL_QUOTERS: dict[str, Quoter] = {
    "auto": quote_powershell,
    "single": quote_powershell,
    "double": _powershell_double,
    "backtick": backtick_escape,
}
# cmd.exe has no single-quote concept; both explicit styles wrap in double quotes.
CMD_QUOTERS: dict[str, Quoter] = {
    "auto": quote_cmd,
    "single": _cmd_double,
    "double": _cmd_double,
    "backtick": backtick_escape,
}


@dataclass(frozen=True, slots=True)
class Shell:
    """A resolved shell and how to run/quote a command through it."""

    name: str
    executable: str
    command_args: tuple[str, ...]
    quoters: Mapping[str, Quoter]

    def build_argv(self, command: str) -> list[str]:
        """Return the argv to run ``command`` through this shell."""
        return [self.executable, *self.command_args, command]

    def quote_as(self, style: str, value: str) -> str:
        """Quote ``value`` in ``style`` (falling back to ``auto``)."""
        quoter = self.quoters.get(style) or self.quoters["auto"]
        return quoter(value)


def detect_shell(preference: str = "auto") -> Shell:
    """Resolve a shell by preference (``auto`` | ``bash`` | ``powershell`` | ``cmd``)."""
    builders: dict[str, Callable[[], Shell | None]] = {
        "bash": _bash_shell,
        "powershell": _powershell_shell,
        "cmd": _cmd_shell,
    }

    if preference != "auto":
        if preference not in builders:
            raise ShellNotFoundError(f"Unknown shell preference: {preference!r}")
        shell = builders[preference]()
        if shell is None:
            raise ShellNotFoundError(f"Requested shell {preference!r} was not found")
        return shell

    for name in ("bash", "powershell", "cmd"):
        shell = builders[name]()
        if shell is not None:
            return shell
    raise ShellNotFoundError("No supported shell found")


def _bash_shell() -> Shell | None:
    path = _find_bash()
    if path is None:
        return None
    return Shell(name="bash", executable=path, command_args=("-c",), quoters=BASH_QUOTERS)


def _powershell_shell() -> Shell | None:
    path = _find_powershell()
    if path is None:
        return None
    return Shell(
        name="powershell",
        executable=path,
        command_args=("-NoProfile", "-Command"),
        quoters=POWERSHELL_QUOTERS,
    )


def _cmd_shell() -> Shell | None:
    path = _find_cmd()
    if path is None:
        return None
    return Shell(name="cmd", executable=path, command_args=("/c",), quoters=CMD_QUOTERS)


def _find_bash() -> str | None:
    for candidate in _git_bash_candidates():
        if candidate.is_file():
            return str(candidate)
    return shutil.which("bash")


def _find_powershell() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell")


def _find_cmd() -> str | None:
    comspec = os.environ.get("COMSPEC")
    if comspec and Path(comspec).is_file():
        return comspec
    return shutil.which("cmd")


def _git_bash_candidates() -> list[Path]:
    candidates: list[Path] = []
    for env_var in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "LOCALAPPDATA"):
        base = os.environ.get(env_var)
        if not base:
            continue
        root = Path(base)
        prefixes = [root / "Git"]
        if env_var == "LOCALAPPDATA":
            prefixes = [root / "Programs" / "Git"]
        for prefix in prefixes:
            candidates.append(prefix / "bin" / "bash.exe")
            candidates.append(prefix / "usr" / "bin" / "bash.exe")
    return candidates
