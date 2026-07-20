"""POSIX PTY-backed connector session with interactive command forwarding."""

from __future__ import annotations

import contextlib
import getpass
import os
import re
import secrets
import select
import shutil
import signal
import sys
from collections.abc import Iterator

from commandbook.connectors.detector import hinted_or_docker_shell, shell_from_probe
from commandbook.connectors.models import (
    ConnectorError,
    ConnectorKind,
    DetectedShell,
    ResolvedConnector,
)
from commandbook.connectors.parser import docker_argv

try:
    import pexpect  # pyright: ignore[reportMissingModuleSource] - package ships no typing metadata
except ImportError:  # pragma: no cover - exercised on unsupported platforms
    pexpect = None  # type: ignore[assignment]


class PtySession:
    """One interactive shell process owned by a connector."""

    def __init__(self, connector: ResolvedConnector) -> None:
        self.connector = connector
        self.shell: DetectedShell | None = None
        self._child: object | None = None

    @property
    def alive(self) -> bool:
        child = self._child
        return bool(child is not None and child.isalive())  # type: ignore[union-attr]

    def start(self) -> DetectedShell:
        if os.name == "nt" or pexpect is None:
            raise ConnectorError("Connectors require a POSIX PTY (Linux, macOS, or WSL)")
        if self.alive and self.shell is not None:
            return self.shell

        hint = hinted_or_docker_shell(self.connector)
        argv = self._spawn_argv(hint)
        executable = shutil.which(argv[0]) or argv[0]
        try:
            child = pexpect.spawn(
                executable,
                argv[1:],
                cwd=self.connector.cwd,
                encoding="utf-8",
                codec_errors="replace",
                echo=False,
                timeout=30,
            )
        except (OSError, pexpect.ExceptionPexpect) as exc:
            raise ConnectorError(f"Could not start connector: {exc}") from exc
        self._child = child
        self._wait_until_ready(child)
        self.shell = hint or self._detect_live_shell(child)
        return self.shell

    def _spawn_argv(self, shell: DetectedShell | None) -> list[str]:
        connector = self.connector
        if connector.kind in (ConnectorKind.DOCKER, ConnectorKind.DOCKER_COMPOSE):
            if shell is None:
                raise ConnectorError("Docker shell detection did not produce a shell")
            argv = docker_argv(connector, shell.executable, interactive=True)
            argv.extend(_interactive_shell_args(shell, docker=True))
            return argv
        argv = list(connector.argv)
        if connector.kind is ConnectorKind.SHELL and len(argv) == 1 and shell is not None:
            argv.extend(_interactive_shell_args(shell, docker=False))
        return argv

    @staticmethod
    def _wait_until_ready(child: object) -> None:
        assert pexpect is not None
        patterns = [
            r"(?i)are you sure you want to continue connecting.*\?",
            r"(?i)(?:password|passphrase).*:\s*$",
            r"(?m)[^\r\n]*[#$>]\s*$",
            pexpect.EOF,
            pexpect.TIMEOUT,
        ]
        while True:
            matched = child.expect(patterns, timeout=30)  # type: ignore[union-attr]
            before = child.before or ""  # type: ignore[union-attr]
            if before:
                sys.stdout.write(before)
                sys.stdout.flush()
            if matched == 0:
                answer = input("Accept remote host key? [yes/no] ").strip() or "no"
                child.sendline(answer)  # type: ignore[union-attr]
            elif matched == 1:
                child.sendline(getpass.getpass("Password/passphrase: "))  # type: ignore[union-attr]
            elif matched == 2:
                return
            elif matched == 3:
                raise ConnectorError("Connector exited before opening a shell")
            else:
                raise ConnectorError("Timed out waiting for the connector shell prompt")

    @staticmethod
    def _detect_live_shell(child: object) -> DetectedShell:
        marker = f"__CB_SHELL_{secrets.token_hex(8)}__"
        child.sendline(f"echo {marker}$0")  # type: ignore[union-attr]
        values: list[str] = []
        for _ in range(3):
            try:
                child.expect(re.escape(marker) + r"([^\r\n]*)", timeout=5)  # type: ignore[union-attr]
            except Exception as exc:
                raise ConnectorError("Could not detect the connector shell") from exc
            value = str(child.match.group(1))  # type: ignore[union-attr]
            values.append(value)
            detected = shell_from_probe(value)
            if detected is not None:
                return detected
            if value.strip() == "":
                powershell = shell_from_probe("pwsh")
                assert powershell is not None
                return powershell
        raise ConnectorError(f"Unsupported connector shell: {values[-1].strip() or 'unknown'}")

    def run(self, command: str, *, cwd: str | None = None) -> int:
        shell = self.start()
        child = self._child
        assert child is not None
        marker = f"__CB_DONE_{secrets.token_hex(16)}__"
        framed = _frame_command(shell, command, cwd, marker)
        child.sendline(framed)  # type: ignore[union-attr]
        return self._bridge_until_marker(marker)

    def _bridge_until_marker(self, marker: str) -> int:
        child = self._child
        assert child is not None
        child_fd = child.child_fd  # type: ignore[union-attr]
        marker_re = re.compile(rb"(?:\r?\n)" + re.escape(marker.encode()) + rb":(-?\d+)\r?\n")
        pending = bytearray()
        stdin_fd = sys.stdin.fileno() if sys.stdin.isatty() else None
        stdout_fd = sys.stdout.fileno()
        with _raw_terminal(stdin_fd), _forward_window_size(child, stdin_fd):
            while True:
                watched = [child_fd]
                if stdin_fd is not None:
                    watched.append(stdin_fd)
                readable, _, _ = select.select(watched, [], [], 0.25)
                if stdin_fd is not None and stdin_fd in readable:
                    data = os.read(stdin_fd, 4096)
                    if data:
                        os.write(child_fd, data)
                if child_fd not in readable:
                    if not child.isalive():  # type: ignore[union-attr]
                        _write_bytes(stdout_fd, pending)
                        raise ConnectorError("Connector closed before the command completed")
                    continue
                try:
                    data = os.read(child_fd, 4096)
                except OSError as exc:
                    _write_bytes(stdout_fd, pending)
                    raise ConnectorError("Connector PTY closed unexpectedly") from exc
                if not data:
                    _write_bytes(stdout_fd, pending)
                    raise ConnectorError("Connector closed before the command completed")
                pending.extend(data)
                match = marker_re.search(pending)
                if match is not None:
                    _write_bytes(stdout_fd, pending[: match.start()])
                    return int(match.group(1))
                if len(pending) > 2048:
                    flush_size = len(pending) - 512
                    _write_bytes(stdout_fd, pending[:flush_size])
                    del pending[:flush_size]

    def close(self) -> None:
        child = self._child
        self._child = None
        self.shell = None
        if child is None:
            return
        if child.isalive():  # type: ignore[union-attr]
            child.sendline("exit")  # type: ignore[union-attr]
            try:
                child.expect(pexpect.EOF, timeout=2)  # type: ignore[union-attr]
            except Exception:
                child.terminate(force=True)  # type: ignore[union-attr]
        child.close(force=True)  # type: ignore[union-attr]


def _interactive_shell_args(shell: DetectedShell, *, docker: bool) -> list[str]:
    if shell.dialect == "powershell":
        return ["-NoLogo", "-NoProfile", "-NoExit"]
    if shell.name == "bash":
        return ["--noprofile", "--norc", "-i"] if not docker else ["-i"]
    return ["-i"]


def _frame_command(shell: DetectedShell, command: str, cwd: str | None, marker: str) -> str:
    if shell.dialect == "powershell":
        prefix = f"Push-Location -LiteralPath {shell.quote_as('single', cwd)}\n" if cwd else ""
        restore = "Pop-Location\n" if cwd else ""
        return (
            f"{prefix}$global:LASTEXITCODE = 0\n& {{\n{command}\n}}\n"
            "$__cb_success = $?\n"
            "$__cb_status = if ($__cb_success) { $LASTEXITCODE } "
            "elseif ($LASTEXITCODE -ne 0) { $LASTEXITCODE } else { 1 }\n"
            f'{restore}Write-Output "`n{marker}:$__cb_status"'
        )
    if cwd:
        quoted = shell.quote_as("auto", cwd)
        return (
            f"__cb_old=$PWD\ncd -- {quoted}\n__cb_cd=$?\n"
            f"if [ $__cb_cd -eq 0 ]; then\n{command}\n__cb_status=$?\n"
            'else\n__cb_status=$__cb_cd\nfi\ncd -- "$__cb_old"\n'
            f"unset __cb_old __cb_cd; printf '\\n{marker}:%s\\n' \"$__cb_status\""
        )
    return f"{command}\n__cb_status=$?\nprintf '\\n{marker}:%s\\n' \"$__cb_status\""


@contextlib.contextmanager
def _raw_terminal(fd: int | None) -> Iterator[None]:
    if fd is None:
        yield
        return
    import termios
    import tty

    previous = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, previous)


def _write_bytes(fd: int, data: bytes | bytearray) -> None:
    if data:
        os.write(fd, bytes(data))


@contextlib.contextmanager
def _forward_window_size(child: object, stdin_fd: int | None) -> Iterator[None]:
    if stdin_fd is None or not hasattr(signal, "SIGWINCH"):
        yield
        return

    def resize(_signum: int = 0, _frame: object | None = None) -> None:
        try:
            size = os.get_terminal_size(stdin_fd)
            child.setwinsize(size.lines, size.columns)  # type: ignore[union-attr]
        except OSError:
            pass

    previous = signal.getsignal(signal.SIGWINCH)
    resize()
    signal.signal(signal.SIGWINCH, resize)
    try:
        yield
    finally:
        signal.signal(signal.SIGWINCH, previous)
