"""
REST API connector for tracking API state.

Captures request/response logs and manages API state through configured endpoints.
"""

import httpx
from typing import Any, Optional
from datetime import datetime

from agent_rollback.connectors.base import BaseConnector


class APIConnector(BaseConnector):
    """Connector for REST API state tracking.

    Captures API state by calling configured state endpoints and logging
    request/response pairs. Supports restoration via configured restore endpoints.
    """

    connector_type: str = "api"

    def __init__(self, connector_id: str, config: Optional[dict[str, Any]] = None):
        """Initialize the API connector.

        Config options:
            - base_url: Base URL for the API
            - state_endpoint: Endpoint to GET current state (e.g., /api/state)
            - restore_endpoint: Endpoint to POST state for restoration
            - headers: Default headers to include in requests
            - timeout: Request timeout in seconds
            - auth: Authentication configuration (type, credentials)
        """
        super().__init__(connector_id, config)
        self.base_url = self.config.get("base_url", "").rstrip("/")
        self.state_endpoint = self.config.get("state_endpoint", "/state")
        self.restore_endpoint = self.config.get("restore_endpoint", "/state/restore")
        self.headers = self.config.get("headers", {})
        self.timeout = self.config.get("timeout", 30)
        self._client: Optional[httpx.AsyncClient] = None
        self._request_log: list[dict[str, Any]] = []

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self.headers,
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def capture_state(self) -> dict[str, Any]:
        """Capture the current API state.

        Returns:
            Dictionary containing the API state
        """
        state = {
            "timestamp": datetime.utcnow().isoformat(),
            "base_url": self.base_url,
            "metadata": {
                "connector_type": self.connector_type,
                "connector_id": self.connector_id,
            },
        }

        if self.base_url and self.state_endpoint:
            try:
                client = await self._get_client()
                response = await client.get(self.state_endpoint)
                response.raise_for_status()
                state["data"] = response.json()
                state["status"] = "captured"
            except Exception as e:
                state["data"] = {}
                state["status"] = "error"
                state["error"] = str(e)
        else:
            # No state endpoint configured - return request log
            state["data"] = {"request_log": self._request_log.copy()}
            state["status"] = "log_only"

        return state

    async def restore_state(self, state: dict[str, Any]) -> bool:
        """Restore the API to a previous state.

        Args:
            state: The state to restore

        Returns:
            True if restoration was successful
        """
        if not self.base_url or not self.restore_endpoint:
            return False

        data = state.get("data", {})
        if not data or state.get("status") == "log_only":
            # Can't restore from log-only state
            return False

        try:
            client = await self._get_client()
            response = await client.post(self.restore_endpoint, json=data)
            response.raise_for_status()
            return True
        except Exception:
            return False

    async def validate_state(self, state: dict[str, Any]) -> bool:
        """Validate that an API state can be restored.

        Args:
            state: The state to validate

        Returns:
            True if the state is valid
        """
        if state.get("status") == "log_only":
            return False  # Log-only states can't be restored

        if state.get("status") == "error":
            return False

        return "data" in state

    async def make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        log: bool = True,
    ) -> dict[str, Any]:
        """Make an API request and optionally log it.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            endpoint: API endpoint
            data: Request body data
            headers: Additional headers
            log: Whether to log this request

        Returns:
            Dictionary with response data
        """
        client = await self._get_client()
        request_info = {
            "timestamp": datetime.utcnow().isoformat(),
            "method": method,
            "endpoint": endpoint,
            "data": data,
            "headers": headers,
        }

        try:
            if method.upper() == "GET":
                response = await client.get(endpoint, headers=headers)
            elif method.upper() == "POST":
                response = await client.post(endpoint, json=data, headers=headers)
            elif method.upper() == "PUT":
                response = await client.put(endpoint, json=data, headers=headers)
            elif method.upper() == "DELETE":
                response = await client.delete(endpoint, headers=headers)
            elif method.upper() == "PATCH":
                response = await client.patch(endpoint, json=data, headers=headers)
            else:
                response = await client.request(method, endpoint, json=data, headers=headers)

            result = {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "success": response.is_success,
            }

            try:
                result["data"] = response.json()
            except Exception:
                result["data"] = response.text

        except Exception as e:
            result = {
                "status_code": None,
                "headers": {},
                "success": False,
                "error": str(e),
            }

        if log:
            self._request_log.append({
                "request": request_info,
                "response": result,
            })

        return result

    def get_request_log(self) -> list[dict[str, Any]]:
        """Get the request log.

        Returns:
            List of logged request/response pairs
        """
        return self._request_log.copy()

    def clear_request_log(self) -> None:
        """Clear the request log."""
        self._request_log.clear()

    async def replay_requests(
        self,
        log: list[dict[str, Any]],
        stop_on_error: bool = True,
    ) -> list[dict[str, Any]]:
        """Replay a sequence of logged requests.

        Args:
            log: List of logged request/response pairs
            stop_on_error: Whether to stop on first error

        Returns:
            List of results for each replayed request
        """
        results = []
        for entry in log:
            request = entry.get("request", {})
            result = await self.make_request(
                method=request.get("method", "GET"),
                endpoint=request.get("endpoint", "/"),
                data=request.get("data"),
                headers=request.get("headers"),
                log=False,
            )
            results.append(result)

            if stop_on_error and not result.get("success"):
                break

        return results
