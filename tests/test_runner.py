"""Tests for command running and working-directory resolution."""

from __future__ import annotations

import shlex
import sys

from commandbook.config.models import Command, Group, Placeholder
from commandbook.shell.detect import Shell
from commandbook.shell.runner import resolve_cwd, run_command

# A shell that runs Python code, so tests are host-independent.
PY_SHELL = Shell(
    name="python",
    executable=sys.executable,
    command_args=("-c",),
    quoters={"auto": shlex.quote, "single": shlex.quote, "double": shlex.quote},
)


def test_run_command_returns_exit_code():
    assert run_command(PY_SHELL, "import sys; sys.exit(0)") == 0
    assert run_command(PY_SHELL, "import sys; sys.exit(3)") == 3


def test_run_command_uses_cwd(tmp_path, capfd):
    code = "import os; print(os.getcwd())"
    run_command(PY_SHELL, code, cwd=str(tmp_path))
    out = capfd.readouterr().out.strip()
    assert out == str(tmp_path)


def test_resolve_cwd_from_directory_placeholder():
    command = Command(
        id="c",
        name="C",
        template="x",
        cwd_from="dir",
        placeholders=[Placeholder(name="dir", type="directory")],
    )
    assert resolve_cwd(command, None, {"dir": "/work/proj"}) == "/work/proj"


def test_resolve_cwd_from_file_placeholder_uses_parent():
    command = Command(
        id="c",
        name="C",
        template="x",
        cwd_from="f",
        placeholders=[Placeholder(name="f", type="file")],
    )
    resolved = resolve_cwd(command, None, {"f": "/work/proj/main.py"})
    assert resolved in ("/work/proj", "\\work\\proj")


def test_resolve_cwd_prefers_command_then_group():
    command = Command(id="c", name="C", template="x", cwd="/from/command")
    group = Group(name="G", cwd="/from/group")
    assert resolve_cwd(command, group, {}) == "/from/command"

    command_no_cwd = Command(id="c2", name="C2", template="x")
    assert resolve_cwd(command_no_cwd, group, {}) == "/from/group"


def test_resolve_cwd_defaults_to_none():
    command = Command(id="c", name="C", template="x")
    assert resolve_cwd(command, None, {}) is None
