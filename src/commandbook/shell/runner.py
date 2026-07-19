"""Running assembled commands and resolving their working directory.

The command runs with inherited stdin/stdout/stderr so it is fully interactive.
The TUI wraps :func:`run_command` in ``App.suspend()`` to drop to the real
terminal for the duration of the run and then resume.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from commandbook.shell.detect import Shell

if TYPE_CHECKING:
    from commandbook.config.models import Command, Group


def run_command(
    shell: Shell,
    command: str,
    *,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    """Run ``command`` through ``shell`` interactively; return the exit code."""
    completed = subprocess.run(  # noqa: S603 — argv is built by the trusted shell wrapper
        shell.build_argv(command),
        cwd=cwd,
        env=dict(env) if env is not None else None,
        check=False,
    )
    return completed.returncode


def resolve_cwd(
    command: Command,
    group: Group | None,
    values: Mapping[str, object],
) -> str | None:
    """Resolve the working directory for a run.

    Priority: a ``cwd_from`` placeholder value (a file's parent, or a directory)
    -> ``command.cwd`` -> ``group.cwd`` -> ``None`` (inherit the current directory).
    """
    if command.cwd_from:
        raw = values.get(command.cwd_from)
        if raw:
            placeholder = command.placeholder(command.cwd_from)
            if placeholder is not None and placeholder.type == "file":
                return str(Path(str(raw)).parent)
            return str(raw)
    if command.cwd:
        return command.cwd
    if group is not None and group.cwd:
        return group.cwd
    return None
