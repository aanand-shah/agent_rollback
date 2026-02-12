"""
Connectors for external system integration.

Each connector provides a standardized interface for:
- Capturing state snapshots
- Restoring state from snapshots
- Validating state changes
"""

from agent_rollback.connectors.base import BaseConnector, ConnectorRegistry
from agent_rollback.connectors.database import DatabaseConnector
from agent_rollback.connectors.filesystem import FileSystemConnector
from agent_rollback.connectors.api import APIConnector
from agent_rollback.connectors.memory import MemoryConnector

__all__ = [
    "BaseConnector",
    "ConnectorRegistry",
    "DatabaseConnector",
    "FileSystemConnector",
    "APIConnector",
    "MemoryConnector",
]
