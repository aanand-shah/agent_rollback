"""
In-memory state connector for tracking volatile state.

Supports local in-memory state and Redis-based distributed state.
"""

import json
from typing import Any, Optional
from datetime import datetime
from copy import deepcopy

from agent_rollback.connectors.base import BaseConnector


class MemoryConnector(BaseConnector):
    """Connector for in-memory state tracking.

    Captures and manages state stored in memory, optionally backed by Redis
    for distributed state management.
    """

    connector_type: str = "memory"

    def __init__(self, connector_id: str, config: Optional[dict[str, Any]] = None):
        """Initialize the memory connector.

        Config options:
            - redis_url: Optional Redis URL for distributed state
            - key_prefix: Prefix for Redis keys
            - ttl: Time-to-live for Redis keys (seconds)
            - namespace: Namespace for organizing state
        """
        super().__init__(connector_id, config)
        self.redis_url = self.config.get("redis_url")
        self.key_prefix = self.config.get("key_prefix", "agent_rollback")
        self.ttl = self.config.get("ttl")
        self.namespace = self.config.get("namespace", "default")
        self._state: dict[str, Any] = {}
        self._redis_client = None

    async def connect_redis(self) -> bool:
        """Connect to Redis if configured.

        Returns:
            True if connected successfully or Redis not configured
        """
        if not self.redis_url:
            return True

        try:
            import redis.asyncio as redis
            self._redis_client = redis.from_url(self.redis_url)
            await self._redis_client.ping()
            return True
        except Exception:
            self._redis_client = None
            return False

    async def close(self) -> None:
        """Close Redis connection if open."""
        if self._redis_client:
            await self._redis_client.close()
            self._redis_client = None

    async def capture_state(self) -> dict[str, Any]:
        """Capture the current memory state.

        Returns:
            Dictionary containing the in-memory state
        """
        state = {
            "timestamp": datetime.utcnow().isoformat(),
            "namespace": self.namespace,
            "metadata": {
                "connector_type": self.connector_type,
                "connector_id": self.connector_id,
                "redis_enabled": self._redis_client is not None,
            },
        }

        if self._redis_client:
            state["data"] = await self._capture_redis_state()
        else:
            state["data"] = deepcopy(self._state)

        return state

    async def restore_state(self, state: dict[str, Any]) -> bool:
        """Restore memory to a previous state.

        Args:
            state: The state to restore

        Returns:
            True if restoration was successful
        """
        try:
            data = state.get("data", {})

            if self._redis_client:
                await self._restore_redis_state(data)
            else:
                self._state = deepcopy(data)

            return True
        except Exception:
            return False

    async def validate_state(self, state: dict[str, Any]) -> bool:
        """Validate that a memory state can be restored.

        Args:
            state: The state to validate

        Returns:
            True if the state is valid
        """
        return "data" in state and isinstance(state.get("data"), dict)

    async def _capture_redis_state(self) -> dict[str, Any]:
        """Capture state from Redis.

        Returns:
            Dictionary with Redis key-value pairs
        """
        if not self._redis_client:
            return {}

        pattern = f"{self.key_prefix}:{self.namespace}:*"
        state = {}

        async for key in self._redis_client.scan_iter(pattern):
            key_str = key.decode() if isinstance(key, bytes) else key
            short_key = key_str.replace(f"{self.key_prefix}:{self.namespace}:", "")
            value = await self._redis_client.get(key)
            if value:
                try:
                    state[short_key] = json.loads(value)
                except json.JSONDecodeError:
                    state[short_key] = value.decode() if isinstance(value, bytes) else value

        return state

    async def _restore_redis_state(self, data: dict[str, Any]) -> None:
        """Restore state to Redis.

        Args:
            data: Dictionary with key-value pairs to restore
        """
        if not self._redis_client:
            return

        # Clear existing keys in namespace
        pattern = f"{self.key_prefix}:{self.namespace}:*"
        async for key in self._redis_client.scan_iter(pattern):
            await self._redis_client.delete(key)

        # Set new state
        for key, value in data.items():
            full_key = f"{self.key_prefix}:{self.namespace}:{key}"
            serialized = json.dumps(value) if not isinstance(value, str) else value
            if self.ttl:
                await self._redis_client.setex(full_key, self.ttl, serialized)
            else:
                await self._redis_client.set(full_key, serialized)

    # Convenience methods for local state management

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from local state.

        Args:
            key: The key to retrieve
            default: Default value if key doesn't exist

        Returns:
            The value or default
        """
        return self._state.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a value in local state.

        Args:
            key: The key to set
            value: The value to store
        """
        self._state[key] = value

    def delete(self, key: str) -> bool:
        """Delete a key from local state.

        Args:
            key: The key to delete

        Returns:
            True if key existed and was deleted
        """
        if key in self._state:
            del self._state[key]
            return True
        return False

    def clear(self) -> None:
        """Clear all local state."""
        self._state.clear()

    def keys(self) -> list[str]:
        """Get all keys in local state.

        Returns:
            List of keys
        """
        return list(self._state.keys())

    def items(self) -> list[tuple[str, Any]]:
        """Get all items in local state.

        Returns:
            List of (key, value) tuples
        """
        return list(self._state.items())

    async def get_async(self, key: str, default: Any = None) -> Any:
        """Get a value, checking Redis if configured.

        Args:
            key: The key to retrieve
            default: Default value if key doesn't exist

        Returns:
            The value or default
        """
        if self._redis_client:
            full_key = f"{self.key_prefix}:{self.namespace}:{key}"
            value = await self._redis_client.get(full_key)
            if value:
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value.decode() if isinstance(value, bytes) else value
            return default
        return self.get(key, default)

    async def set_async(self, key: str, value: Any) -> None:
        """Set a value, updating Redis if configured.

        Args:
            key: The key to set
            value: The value to store
        """
        self._state[key] = value
        if self._redis_client:
            full_key = f"{self.key_prefix}:{self.namespace}:{key}"
            serialized = json.dumps(value) if not isinstance(value, str) else value
            if self.ttl:
                await self._redis_client.setex(full_key, self.ttl, serialized)
            else:
                await self._redis_client.set(full_key, serialized)

    async def delete_async(self, key: str) -> bool:
        """Delete a key, removing from Redis if configured.

        Args:
            key: The key to delete

        Returns:
            True if key existed and was deleted
        """
        local_existed = self.delete(key)
        if self._redis_client:
            full_key = f"{self.key_prefix}:{self.namespace}:{key}"
            redis_deleted = await self._redis_client.delete(full_key)
            return local_existed or redis_deleted > 0
        return local_existed
