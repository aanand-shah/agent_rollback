"""
Base connector interface for external system integration.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class BaseConnector(ABC):
    """Abstract base class for system connectors.

    Connectors provide a standardized interface for capturing and restoring
    state in external systems (databases, file systems, APIs, etc.).
    """

    connector_type: str = "base"

    def __init__(self, connector_id: str, config: Optional[dict[str, Any]] = None):
        """Initialize the connector.

        Args:
            connector_id: Unique identifier for this connector instance
            config: Configuration options for the connector
        """
        self.connector_id = connector_id
        self.config = config or {}

    @abstractmethod
    async def capture_state(self) -> dict[str, Any]:
        """Capture the current state of the connected system.

        Returns:
            A dictionary containing the serialized state
        """
        pass

    @abstractmethod
    async def restore_state(self, state: dict[str, Any]) -> bool:
        """Restore the system to a previous state.

        Args:
            state: The state to restore, as returned by capture_state()

        Returns:
            True if restoration was successful, False otherwise
        """
        pass

    @abstractmethod
    async def validate_state(self, state: dict[str, Any]) -> bool:
        """Validate that a state can be restored.

        Args:
            state: The state to validate

        Returns:
            True if the state is valid and can be restored
        """
        pass

    async def diff_states(
        self, state_a: dict[str, Any], state_b: dict[str, Any]
    ) -> dict[str, Any]:
        """Compute the difference between two states.

        Args:
            state_a: The first state
            state_b: The second state

        Returns:
            A dictionary describing the differences
        """
        # Default implementation using generic diff
        from agent_rollback.utils.diff import compute_diff
        return compute_diff(state_a, state_b)

    def get_info(self) -> dict[str, Any]:
        """Get connector information.

        Returns:
            Dictionary with connector metadata
        """
        return {
            "connector_type": self.connector_type,
            "connector_id": self.connector_id,
            "config": self.config,
        }


class ConnectorRegistry:
    """Registry for managing connector instances."""

    def __init__(self):
        self._connectors: dict[str, BaseConnector] = {}
        self._connector_classes: dict[str, type[BaseConnector]] = {}

    def register_class(
        self, connector_type: str, connector_class: type[BaseConnector]
    ) -> None:
        """Register a connector class for a given type.

        Args:
            connector_type: Type identifier for the connector
            connector_class: The connector class to register
        """
        self._connector_classes[connector_type] = connector_class

    def create_connector(
        self,
        connector_type: str,
        connector_id: str,
        config: Optional[dict[str, Any]] = None,
    ) -> BaseConnector:
        """Create a new connector instance.

        Args:
            connector_type: Type of connector to create
            connector_id: Unique identifier for the instance
            config: Configuration for the connector

        Returns:
            The created connector instance

        Raises:
            ValueError: If connector type is not registered
        """
        if connector_type not in self._connector_classes:
            raise ValueError(f"Unknown connector type: {connector_type}")

        connector = self._connector_classes[connector_type](connector_id, config)
        key = f"{connector_type}:{connector_id}"
        self._connectors[key] = connector
        return connector

    def get_connector(
        self, connector_type: str, connector_id: str
    ) -> Optional[BaseConnector]:
        """Get a registered connector instance.

        Args:
            connector_type: Type of connector
            connector_id: Unique identifier for the instance

        Returns:
            The connector instance, or None if not found
        """
        key = f"{connector_type}:{connector_id}"
        return self._connectors.get(key)

    def register_connector(self, connector: BaseConnector) -> None:
        """Register an existing connector instance.

        Args:
            connector: The connector to register
        """
        key = f"{connector.connector_type}:{connector.connector_id}"
        self._connectors[key] = connector

    def unregister_connector(
        self, connector_type: str, connector_id: str
    ) -> Optional[BaseConnector]:
        """Unregister a connector instance.

        Args:
            connector_type: Type of connector
            connector_id: Unique identifier for the instance

        Returns:
            The removed connector, or None if not found
        """
        key = f"{connector_type}:{connector_id}"
        return self._connectors.pop(key, None)

    def list_connectors(
        self, connector_type: Optional[str] = None
    ) -> list[BaseConnector]:
        """List all registered connectors.

        Args:
            connector_type: Optional filter by type

        Returns:
            List of connector instances
        """
        connectors = list(self._connectors.values())
        if connector_type:
            connectors = [c for c in connectors if c.connector_type == connector_type]
        return connectors

    def get_connector_types(self) -> list[str]:
        """Get all registered connector types.

        Returns:
            List of connector type identifiers
        """
        return list(self._connector_classes.keys())


# Global registry instance
_registry = ConnectorRegistry()


def get_registry() -> ConnectorRegistry:
    """Get the global connector registry."""
    return _registry
