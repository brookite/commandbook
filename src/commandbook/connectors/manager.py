"""High-level persistent and next-command connector lifecycle."""

from __future__ import annotations

from commandbook.connectors.models import ConnectorError, DetectedShell, ResolvedConnector
from commandbook.connectors.session import PtySession


class ConnectionManager:
    """Own the selected connector and at most one PTY session."""

    def __init__(self) -> None:
        self.connector: ResolvedConnector | None = None
        self._session: PtySession | None = None

    @property
    def connected(self) -> bool:
        return bool(
            self.connector and self.connector.persistent and self._session and self._session.alive
        )

    @property
    def shell(self) -> DetectedShell | None:
        return self._session.shell if self._session is not None else None

    def select(self, connector: ResolvedConnector) -> None:
        self.disconnect()
        self.connector = connector

    def prepare(self) -> DetectedShell:
        if self.connector is None:
            raise RuntimeError("No connector selected")
        if self._session is None:
            self._session = PtySession(self.connector)
        elif self.connector.persistent and not self._session.alive:
            raise ConnectorError("Persistent connector is no longer running; reconnect with Ctrl+S")
        try:
            return self._session.start()
        except Exception:
            self._session.close()
            self._session = None
            raise

    def run(self, command: str, *, cwd: str | None = None) -> int:
        if self.connector is None:
            raise RuntimeError("No connector selected")
        if self._session is None:
            self._session = PtySession(self.connector)
        try:
            return self._session.run(command, cwd=cwd)
        finally:
            if not self.connector.persistent:
                self._session.close()
                self._session = None
                self.connector = None

    def disconnect(self) -> None:
        if self._session is not None:
            self._session.close()
        self._session = None
        self.connector = None
