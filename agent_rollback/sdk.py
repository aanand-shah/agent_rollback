"""
Python SDK for AgentRollback integration.

Provides a high-level client interface and decorators for easy integration
with AI agent applications.
"""

import asyncio
from contextlib import asynccontextmanager
from functools import wraps
from typing import Any, Callable, Optional, TypeVar, ParamSpec
from datetime import datetime

import httpx

from agent_rollback.models import (
    Session,
    SessionCreate,
    SessionStatus,
    Snapshot,
    SnapshotType,
    Action,
    ActionCreate,
    ActionStatus,
    RollbackRequest,
    RollbackResult,
    ReplayRequest,
    ReplayResult,
    DiffResult,
)


P = ParamSpec("P")
T = TypeVar("T")


class AgentRollbackClient:
    """Client for interacting with AgentRollback API or local store.

    Can operate in two modes:
    - API mode: Communicates with a remote AgentRollback server
    - Local mode: Uses local StateStore directly
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        local: bool = False,
        db_path: str = "agent_rollback.db",
    ):
        """Initialize the client.

        Args:
            base_url: Base URL for API mode (e.g., "http://localhost:8000")
            api_key: Optional API key for authentication
            timeout: Request timeout in seconds
            local: If True, use local store instead of API
            db_path: Path to database for local mode
        """
        self.base_url = base_url.rstrip("/") if base_url else None
        self.api_key = api_key
        self.timeout = timeout
        self.local = local
        self.db_path = db_path

        self._client: Optional[httpx.AsyncClient] = None
        self._store = None
        self._tracker = None
        self._recovery = None
        self._current_session: Optional[str] = None

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def connect(self) -> None:
        """Establish connection (API client or local store)."""
        if self.local:
            from agent_rollback.store import StateStore
            from agent_rollback.tracker import StateTracker
            from agent_rollback.recovery import RecoveryEngine

            self._store = StateStore(db_path=self.db_path)
            await self._store.initialize()
            self._tracker = StateTracker(store=self._store)
            self._recovery = RecoveryEngine(store=self._store)
        else:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=self.timeout,
            )

    async def close(self) -> None:
        """Close connections."""
        if self._client:
            await self._client.aclose()
            self._client = None
        if self._store:
            await self._store.close()
            self._store = None

    # Session management

    async def start_session(
        self,
        agent_id: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Session:
        """Start a new tracking session.

        Args:
            agent_id: Identifier for the agent
            metadata: Optional session metadata

        Returns:
            The created session
        """
        if self.local:
            session = await self._tracker.start_session(agent_id, metadata)
        else:
            response = await self._client.post(
                "/api/v1/sessions",
                json={"agent_id": agent_id, "metadata": metadata},
            )
            response.raise_for_status()
            data = response.json()
            session = Session(**data["session"])

        self._current_session = session.id
        return session

    async def end_session(
        self,
        session_id: Optional[str] = None,
        status: SessionStatus = SessionStatus.COMPLETED,
    ) -> Session:
        """End a tracking session.

        Args:
            session_id: Session to end (uses current if None)
            status: Final status

        Returns:
            The updated session
        """
        sid = session_id or self._current_session
        if not sid:
            raise ValueError("No session ID provided and no current session")

        if self.local:
            session = await self._tracker.end_session(sid, status)
        else:
            response = await self._client.delete(
                f"/api/v1/sessions/{sid}",
                params={"status": status.value},
            )
            response.raise_for_status()
            data = response.json()
            session = Session(**data["session"])

        if sid == self._current_session:
            self._current_session = None

        return session

    async def get_session(self, session_id: str) -> Optional[Session]:
        """Get session details.

        Args:
            session_id: Session ID

        Returns:
            The session or None
        """
        if self.local:
            return await self._store.get_session(session_id)
        else:
            response = await self._client.get(f"/api/v1/sessions/{session_id}")
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()
            return Session(**data["session"])

    async def list_sessions(
        self,
        status: Optional[SessionStatus] = None,
        agent_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[Session]:
        """List sessions.

        Args:
            status: Filter by status
            agent_id: Filter by agent
            limit: Maximum results

        Returns:
            List of sessions
        """
        if self.local:
            return await self._store.list_sessions(status=status, agent_id=agent_id, limit=limit)
        else:
            params = {"limit": limit}
            if status:
                params["status"] = status.value
            if agent_id:
                params["agent_id"] = agent_id
            response = await self._client.get("/api/v1/sessions", params=params)
            response.raise_for_status()
            data = response.json()
            return [Session(**s) for s in data["sessions"]]

    # Action recording

    async def record_action(
        self,
        action_type: str,
        action_data: Optional[dict[str, Any]] = None,
        before_state: Optional[dict[str, Any]] = None,
        after_state: Optional[dict[str, Any]] = None,
        connector_type: Optional[str] = None,
        connector_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Action:
        """Record an action.

        Args:
            action_type: Type of action
            action_data: Action parameters
            before_state: State before action
            after_state: State after action
            connector_type: Connector type
            connector_id: Connector ID
            session_id: Session ID (uses current if None)

        Returns:
            The recorded action
        """
        sid = session_id or self._current_session
        if not sid:
            raise ValueError("No session ID provided and no current session")

        if self.local:
            return await self._tracker.record_action(
                action_type=action_type,
                action_data=action_data,
                before_state=before_state,
                after_state=after_state,
                connector_type=connector_type,
                connector_id=connector_id,
                session_id=sid,
            )
        else:
            response = await self._client.post(
                f"/api/v1/sessions/{sid}/actions",
                json={
                    "session_id": sid,
                    "action_type": action_type,
                    "action_data": action_data,
                    "before_state": before_state,
                    "after_state": after_state,
                    "connector_type": connector_type,
                    "connector_id": connector_id,
                },
            )
            response.raise_for_status()
            data = response.json()
            return Action(**data["action"])

    async def list_actions(
        self,
        session_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[Action]:
        """List actions in a session.

        Args:
            session_id: Session ID (uses current if None)
            limit: Maximum results

        Returns:
            List of actions
        """
        sid = session_id or self._current_session
        if not sid:
            raise ValueError("No session ID provided and no current session")

        if self.local:
            return await self._store.list_actions(session_id=sid, limit=limit)
        else:
            response = await self._client.get(
                f"/api/v1/sessions/{sid}/actions",
                params={"limit": limit},
            )
            response.raise_for_status()
            data = response.json()
            return [Action(**a) for a in data["actions"]]

    # Checkpoint management

    async def create_checkpoint(
        self,
        state_data: Optional[dict[str, Any]] = None,
        connector_type: str = "manual",
        connector_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Snapshot:
        """Create a checkpoint.

        Args:
            state_data: State to checkpoint
            connector_type: Connector type
            connector_id: Connector ID
            session_id: Session ID (uses current if None)

        Returns:
            The checkpoint snapshot
        """
        sid = session_id or self._current_session
        if not sid:
            raise ValueError("No session ID provided and no current session")

        if self.local:
            return await self._tracker.create_checkpoint(
                session_id=sid,
                connector_type=connector_type,
                connector_id=connector_id,
                state_data=state_data,
            )
        else:
            response = await self._client.post(
                f"/api/v1/sessions/{sid}/checkpoint",
                json={
                    "connector_type": connector_type,
                    "connector_id": connector_id,
                    "state_data": state_data,
                },
            )
            response.raise_for_status()
            data = response.json()
            return Snapshot(**data["snapshot"])

    async def get_snapshot(self, snapshot_id: str) -> Optional[Snapshot]:
        """Get snapshot details.

        Args:
            snapshot_id: Snapshot ID

        Returns:
            The snapshot or None
        """
        if self.local:
            return await self._store.get_snapshot(snapshot_id)
        else:
            response = await self._client.get(f"/api/v1/snapshots/{snapshot_id}")
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()
            return Snapshot(**data["snapshot"])

    async def list_snapshots(
        self,
        session_id: Optional[str] = None,
        snapshot_type: Optional[SnapshotType] = None,
        limit: int = 100,
    ) -> list[Snapshot]:
        """List snapshots in a session.

        Args:
            session_id: Session ID (uses current if None)
            snapshot_type: Filter by type
            limit: Maximum results

        Returns:
            List of snapshots
        """
        sid = session_id or self._current_session
        if not sid:
            raise ValueError("No session ID provided and no current session")

        if self.local:
            return await self._store.list_snapshots(
                session_id=sid,
                snapshot_type=snapshot_type,
                limit=limit,
            )
        else:
            params = {"limit": limit}
            if snapshot_type:
                params["snapshot_type"] = snapshot_type.value
            response = await self._client.get(
                f"/api/v1/sessions/{sid}/snapshots",
                params=params,
            )
            response.raise_for_status()
            data = response.json()
            return [Snapshot(**s) for s in data["snapshots"]]

    # Recovery operations

    async def rollback(
        self,
        target_snapshot_id: str,
        session_id: Optional[str] = None,
        dry_run: bool = False,
    ) -> RollbackResult:
        """Rollback to a snapshot.

        Args:
            target_snapshot_id: Target snapshot
            session_id: Session ID (uses current if None)
            dry_run: If True, only simulate

        Returns:
            Rollback result
        """
        sid = session_id or self._current_session
        if not sid:
            raise ValueError("No session ID provided and no current session")

        request = RollbackRequest(
            session_id=sid,
            target_snapshot_id=target_snapshot_id,
            dry_run=dry_run,
        )

        if self.local:
            return await self._recovery.rollback(request)
        else:
            response = await self._client.post(
                "/api/v1/rollback",
                json=request.model_dump(),
            )
            response.raise_for_status()
            return RollbackResult(**response.json())

    async def replay(
        self,
        from_snapshot_id: str,
        to_snapshot_id: Optional[str] = None,
        session_id: Optional[str] = None,
        dry_run: bool = False,
    ) -> ReplayResult:
        """Replay actions from a snapshot.

        Args:
            from_snapshot_id: Starting snapshot
            to_snapshot_id: Ending snapshot (None for latest)
            session_id: Session ID (uses current if None)
            dry_run: If True, only simulate

        Returns:
            Replay result
        """
        sid = session_id or self._current_session
        if not sid:
            raise ValueError("No session ID provided and no current session")

        request = ReplayRequest(
            session_id=sid,
            from_snapshot_id=from_snapshot_id,
            to_snapshot_id=to_snapshot_id,
            dry_run=dry_run,
        )

        if self.local:
            return await self._recovery.replay(request)
        else:
            response = await self._client.post(
                "/api/v1/replay",
                json=request.model_dump(),
            )
            response.raise_for_status()
            return ReplayResult(**response.json())

    async def diff(
        self,
        snapshot_a_id: str,
        snapshot_b_id: str,
    ) -> DiffResult:
        """Compare two snapshots.

        Args:
            snapshot_a_id: First snapshot
            snapshot_b_id: Second snapshot

        Returns:
            Diff result
        """
        if self.local:
            return await self._recovery.diff(snapshot_a_id, snapshot_b_id)
        else:
            response = await self._client.get(
                "/api/v1/diff",
                params={
                    "snapshot_a_id": snapshot_a_id,
                    "snapshot_b_id": snapshot_b_id,
                },
            )
            response.raise_for_status()
            return DiffResult(**response.json())

    # Session context manager

    @asynccontextmanager
    async def session(
        self,
        agent_id: str,
        metadata: Optional[dict[str, Any]] = None,
        auto_checkpoint: bool = False,
    ):
        """Context manager for a tracking session.

        Args:
            agent_id: Agent identifier
            metadata: Session metadata
            auto_checkpoint: Create checkpoint on exit

        Yields:
            The session object
        """
        session = await self.start_session(agent_id, metadata)
        try:
            yield session
            if auto_checkpoint:
                await self.create_checkpoint()
            await self.end_session(status=SessionStatus.COMPLETED)
        except Exception:
            await self.end_session(status=SessionStatus.FAILED)
            raise

    @property
    def current_session_id(self) -> Optional[str]:
        """Get the current session ID."""
        return self._current_session


def track_action(
    action_type: str,
    client: Optional[AgentRollbackClient] = None,
    capture_args: bool = True,
    capture_result: bool = True,
    capture_state: Optional[Callable[[], dict[str, Any]]] = None,
):
    """Decorator for tracking function calls as actions.

    Args:
        action_type: Type identifier for the action
        client: AgentRollbackClient instance
        capture_args: Whether to capture function arguments
        capture_result: Whether to capture function result
        capture_state: Optional callable to capture state before/after

    Returns:
        Decorated function
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            nonlocal client
            if client is None:
                raise ValueError("No client provided to @track_action")

            action_data = {}
            if capture_args:
                action_data["args"] = [repr(a) for a in args]
                action_data["kwargs"] = {k: repr(v) for k, v in kwargs.items()}

            before_state = None
            if capture_state:
                before_state = capture_state()

            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                action_data["status"] = "success"
                if capture_result:
                    action_data["result"] = repr(result)
            except Exception as e:
                action_data["status"] = "error"
                action_data["error"] = str(e)
                raise
            finally:
                after_state = None
                if capture_state:
                    after_state = capture_state()

                await client.record_action(
                    action_type=action_type,
                    action_data=action_data,
                    before_state=before_state,
                    after_state=after_state,
                )

            return result

        @wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            return asyncio.get_event_loop().run_until_complete(
                async_wrapper(*args, **kwargs)
            )

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


class TrackedAgent:
    """Base class for agents with automatic tracking.

    Subclass this to create agents with built-in state tracking.
    """

    def __init__(
        self,
        agent_id: str,
        client: Optional[AgentRollbackClient] = None,
        **client_kwargs,
    ):
        """Initialize the tracked agent.

        Args:
            agent_id: Unique identifier for this agent
            client: Optional pre-configured client
            **client_kwargs: Arguments for creating new client
        """
        self.agent_id = agent_id
        self._client = client
        self._client_kwargs = client_kwargs
        self._owns_client = client is None

    async def __aenter__(self):
        """Start tracking session."""
        if self._owns_client:
            self._client = AgentRollbackClient(**self._client_kwargs)
            await self._client.connect()
        await self._client.start_session(self.agent_id)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """End tracking session."""
        status = SessionStatus.FAILED if exc_type else SessionStatus.COMPLETED
        await self._client.end_session(status=status)
        if self._owns_client:
            await self._client.close()

    async def record_action(
        self,
        action_type: str,
        action_data: Optional[dict[str, Any]] = None,
        before_state: Optional[dict[str, Any]] = None,
        after_state: Optional[dict[str, Any]] = None,
    ) -> Action:
        """Record an action."""
        return await self._client.record_action(
            action_type=action_type,
            action_data=action_data,
            before_state=before_state,
            after_state=after_state,
        )

    async def checkpoint(
        self,
        state_data: Optional[dict[str, Any]] = None,
    ) -> Snapshot:
        """Create a checkpoint."""
        return await self._client.create_checkpoint(state_data=state_data)

    @property
    def client(self) -> AgentRollbackClient:
        """Get the underlying client."""
        return self._client
