"""Remote/local connector parsing, shell detection, and session lifecycle."""

from commandbook.connectors.manager import ConnectionManager
from commandbook.connectors.models import ConnectorError, ConnectorKind, ResolvedConnector
from commandbook.connectors.parser import resolve_connector

__all__ = [
    "ConnectionManager",
    "ConnectorError",
    "ConnectorKind",
    "ResolvedConnector",
    "resolve_connector",
]
