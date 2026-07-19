"""Tests for shell detection and quoting."""

from __future__ import annotations

import pytest

from commandbook.shell import detect
from commandbook.shell.detect import (
    BASH_QUOTERS,
    Shell,
    ShellNotFoundError,
    detect_shell,
    quote_cmd,
    quote_powershell,
)


def test_build_argv():
    bash = Shell(
        name="bash", executable="/usr/bin/bash", command_args=("-c",), quoters=BASH_QUOTERS
    )
    assert bash.build_argv("ls -la") == ["/usr/bin/bash", "-c", "ls -la"]


def test_quote_powershell():
    assert quote_powershell("a b") == "'a b'"
    assert quote_powershell("it's") == "'it''s'"


def test_quote_cmd():
    assert quote_cmd("simple") == "simple"
    assert quote_cmd("a b") == '"a b"'
    assert quote_cmd('say "hi"') == '"say ""hi"""'


def test_quote_as_styles():
    bash = Shell(name="bash", executable="/bin/bash", command_args=("-c",), quoters=BASH_QUOTERS)
    assert bash.quote_as("auto", "a b") == "'a b'"
    assert bash.quote_as("single", "a b") == "'a b'"
    assert bash.quote_as("double", "a b") == '"a b"'
    assert bash.quote_as("double", 'a "b" $c') == '"a \\"b\\" \\$c"'
    assert bash.quote_as("backtick", "a b") == "a` b"
    # Unknown style falls back to auto.
    assert bash.quote_as("weird", "a b") == "'a b'"


def test_detect_prefers_bash(monkeypatch):
    monkeypatch.setattr(detect, "_find_bash", lambda: "/usr/bin/bash")
    monkeypatch.setattr(detect, "_find_powershell", lambda: "/usr/bin/pwsh")
    monkeypatch.setattr(detect, "_find_cmd", lambda: None)
    shell = detect_shell("auto")
    assert shell.name == "bash"
    assert shell.build_argv("echo hi") == ["/usr/bin/bash", "-c", "echo hi"]


def test_detect_falls_back_to_powershell(monkeypatch):
    monkeypatch.setattr(detect, "_find_bash", lambda: None)
    monkeypatch.setattr(detect, "_find_powershell", lambda: "pwsh.exe")
    monkeypatch.setattr(detect, "_find_cmd", lambda: "cmd.exe")
    shell = detect_shell("auto")
    assert shell.name == "powershell"
    assert shell.command_args == ("-NoProfile", "-Command")


def test_detect_explicit_missing_raises(monkeypatch):
    monkeypatch.setattr(detect, "_find_bash", lambda: None)
    with pytest.raises(ShellNotFoundError):
        detect_shell("bash")


def test_detect_none_available_raises(monkeypatch):
    monkeypatch.setattr(detect, "_find_bash", lambda: None)
    monkeypatch.setattr(detect, "_find_powershell", lambda: None)
    monkeypatch.setattr(detect, "_find_cmd", lambda: None)
    with pytest.raises(ShellNotFoundError):
        detect_shell("auto")


def test_detect_unknown_preference_raises():
    with pytest.raises(ShellNotFoundError):
        detect_shell("fish")
