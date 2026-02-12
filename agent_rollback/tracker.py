"""
State tracker for intercepting and recording agent actions.

Provides decorators and middleware hooks for automatic state capture.
"""

from datetime import datetime
from typing import Any, Callable, Optional
from functools import wraps
import asyncio

from agent_rollback.models import (
    Session,
    SessionCreate,
    SessionStatus,
    Snapshot,
    SnapshotCreate,
    SnapshotType,
    Action,
    ActionCreate,
    ActionStatus,
)
from agent_rollback.store import StateStore
from agent_rollback.connectors.base import BaseConnector, ConnectorRegistry, get_registry


class StateTracker:
    """Tracks agent state changes across sessions.

    The tracker intercepts agent actions via decorators or explicit calls,
    captures before/after state snapshots, and records everything for
    later recovery.
    """

    def __init__(
        self,
        store: Optional[StateStore] = None,
        registry: Optional[ConnectorRegistry] = None,
        auto_checkpoint_interval: Optional[int] = None,
    ):
        """Initialize the state tracker.

        Args:
            store: State store for persistence (creates default if None)
            registry: Connector registry (uses global if None)
            auto_checkpoint_interval: If set, auto-checkpoint every N actions
        """
        self.store = store or StateStore()
        self.registry = registry or get_registry()
        self.auto_checkpoint_interval = auto_checkpoint_interval
        self._active_sessions: dict[str, Session] = {}
        self._session_action_counts: dict[str, int] = {}
        self._current_session: Optional[str] = None

    async def initialize(self) -> None:
        """Initialize the tracker and underlying store."""
        await self.store.initialize()

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
        session = await self.store.create_session(
            SessionCreate(agent_id=agent_id, metadata=metadata)
        )
        self._active_sessions[session.id] = session
        self._session_action_counts[session.id] = 0
        self._current_session = session.id
        return session

    async def end_session(
        self,
        session_id: Optional[str] = None,
        status: SessionStatus = SessionStatus.COMPLETED,
    ) -> Optional[Session]:
        """End a tracking session.

        Args:
            session_id: Session to end (uses current if None)
            status: Final session status

        Returns:
            The updated session
        """
        sid = session_id or self._current_session
        if not sid:
            return None

        session = await self.store.update_session(
            sid,
            status=status,
            ended_at=datetime.utcnow(),
        )

        self._active_sessions.pop(sid, None)
        self._session_action_counts.pop(sid, None)
        if self._current_session == sid:
            self._current_session = None

        return session

    async def record_action(
        self,
        action_type: str,
        action_data: Optional[dict[str, Any]] = None,
        before_state: Optional[dict[str, Any]] = None,
        after_state: Optional[dict[str, Any]] = None,
        connector_type: Optional[str] = None,
        connector_id: Optional[str] = None,
        session_id: Optional[str] = None,
        parent_action_id: Optional[str] = None,
    ) -> Action:
        """Record an action with optional state snapshots.

        Args:
            action_type: Type of action being performed
            action_data: Parameters/details of the action
            before_state: State before action (for snapshot)
            after_state: State after action (for snapshot)
            connector_type: Type of connector involved
            connector_id: ID of connector involved
            session_id: Session to record in (uses current if None)
            parent_action_id: Parent action for nested operations

        Returns:
            The recorded action
        """
        sid = session_id or self._current_session
        if not sid:
            raise ValueError("No active session. Call start_session() first.")

        action = await self.store.create_action(
            ActionCreate(
                session_id=sid,
                action_type=action_type,
                action_data=action_data,
                before_state=before_state,
                after_state=after_state,
                connector_type=connector_type,
                connector_id=connector_id,
                parent_action_id=parent_action_id,
            )
        )

        # Increment action count and check for auto-checkpoint
        self._session_action_counts[sid] = self._session_action_counts.get(sid, 0) + 1
        if (
            self.auto_checkpoint_interval
            and self._session_action_counts[sid] % self.auto_checkpoint_interval == 0
        ):
            await self.create_checkpoint(session_id=sid)

        return action

    async def record_action_with_connector(
        self,
        action_type: str,
        connector: BaseConnector,
        action_data: Optional[dict[str, Any]] = None,
        session_id: Optional[str] = None,
        parent_action_id: Optional[str] = None,
    ) -> tuple[Action, Snapshot, Snapshot]:
        """Record an action with automatic state capture from connector.

        Args:
            action_type: Type of action being performed
            connector: Connector to capture state from
            action_data: Parameters/details of the action
            session_id: Session to record in (uses current if None)
            parent_action_id: Parent action for nested operations

        Returns:
            Tuple of (action, before_snapshot, after_snapshot)
        """
        sid = session_id or self._current_session
        if not sid:
            raise ValueError("No active session. Call start_session() first.")

        # Capture before state
        before_state = await connector.capture_state()

        # The action happens between these calls (caller is responsible)

        # Create the action record
        action = await self.store.create_action(
            ActionCreate(
                session_id=sid,
                action_type=action_type,
                action_data=action_data,
                before_state=before_state,
                connector_type=connector.connector_type,
                connector_id=connector.connector_id,
                parent_action_id=parent_action_id,
            )
        )

        # Get the before snapshot that was created
        before_snapshot = await self.store.get_snapshot(action.before_snapshot_id) if action.before_snapshot_id else None

        return action, before_snapshot, None  # after_snapshot filled in later

    async def complete_action(
        self,
        action_id: str,
        connector: BaseConnector,
        status: ActionStatus = ActionStatus.COMPLETED,
    ) -> tuple[Action, Snapshot]:
        """Complete an action by capturing the after state.

        Args:
            action_id: Action to complete
            connector: Connector to capture state from
            status: Final action status

        Returns:
            Tuple of (updated_action, after_snapshot)
        """
        action = await self.store.get_action(action_id)
        if not action:
            raise ValueError(f"Action not found: {action_id}")

        # Capture after state
        after_state = await connector.capture_state()
        after_snapshot = await self.store.create_snapshot(
            SnapshotCreate(
                session_id=action.session_id,
                action_id=action_id,
                connector_type=connector.connector_type,
                connector_id=connector.connector_id,
                state_data=after_state,
                snapshot_type=SnapshotType.AFTER,
            )
        )

        # Update action
        action = await self.store.update_action(
            action_id,
            status=status,
            after_snapshot_id=after_snapshot.id,
        )

        return action, after_snapshot

    async def create_checkpoint(
        self,
        session_id: Optional[str] = None,
        connector: Optional[BaseConnector] = None,
        connector_type: Optional[str] = None,
        connector_id: Optional[str] = None,
        state_data: Optional[dict[str, Any]] = None,
    ) -> Snapshot:
        """Create a manual checkpoint snapshot.

        Args:
            session_id: Session to checkpoint (uses current if None)
            connector: Connector to capture state from
            connector_type: Type of connector (if not providing connector)
            connector_id: ID of connector (if not providing connector)
            state_data: State data to checkpoint (if not using connector)

        Returns:
            The checkpoint snapshot
        """
        sid = session_id or self._current_session
        if not sid:
            raise ValueError("No active session. Call start_session() first.")

        if connector:
            checkpoint_state = await connector.capture_state()
            conn_type = connector.connector_type
            conn_id = connector.connector_id
        elif state_data is not None:
            checkpoint_state = state_data
            conn_type = connector_type or "manual"
            conn_id = connector_id
        else:
            checkpoint_state = {"checkpoint": True, "timestamp": datetime.utcnow().isoformat()}
            conn_type = connector_type or "manual"
            conn_id = connector_id

        return await self.store.create_snapshot(
            SnapshotCreate(
                session_id=sid,
                connector_type=conn_type,
                connector_id=conn_id,
                state_data=checkpoint_state,
                snapshot_type=SnapshotType.CHECKPOINT,
            )
        )

    async def create_snapshot(
        self,
        connector: BaseConnector,
        snapshot_type: SnapshotType = SnapshotType.CHECKPOINT,
        session_id: Optional[str] = None,
        action_id: Optional[str] = None,
    ) -> Snapshot:
        """Create a state snapshot from a connector.

        Args:
            connector: Connector to capture state from
            snapshot_type: Type of snapshot
            session_id: Session to associate with (uses current if None)
            action_id: Action to associate with

        Returns:
            The created snapshot
        """
        sid = session_id or self._current_session
        if not sid:
            raise ValueError("No active session. Call start_session() first.")

        state_data = await connector.capture_state()

        return await self.store.create_snapshot(
            SnapshotCreate(
                session_id=sid,
                action_id=action_id,
                connector_type=connector.connector_type,
                connector_id=connector.connector_id,
                state_data=state_data,
                snapshot_type=snapshot_type,
            )
        )

    def get_current_session(self) -> Optional[str]:
        """Get the current active session ID."""
        return self._current_session

    def set_current_session(self, session_id: str) -> None:
        """Set the current active session.

        Args:
            session_id: Session ID to make current
        """
        self._current_session = session_id

    async def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID.

        Args:
            session_id: Session ID

        Returns:
            The session or None
        """
        return await self.store.get_session(session_id)

    async def list_sessions(
        self,
        status: Optional[SessionStatus] = None,
        agent_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[Session]:
        """List sessions with optional filtering.

        Args:
            status: Filter by status
            agent_id: Filter by agent
            limit: Maximum number to return

        Returns:
            List of sessions
        """
        return await self.store.list_sessions(
            status=status,
            agent_id=agent_id,
            limit=limit,
        )

    async def get_actions(
        self,
        session_id: str,
        limit: int = 100,
    ) -> list[Action]:
        """Get actions for a session.

        Args:
            session_id: Session ID
            limit: Maximum number to return

        Returns:
            List of actions
        """
        return await self.store.list_actions(session_id=session_id, limit=limit)

    async def get_snapshots(
        self,
        session_id: str,
        limit: int = 100,
    ) -> list[Snapshot]:
        """Get snapshots for a session.

        Args:
            session_id: Session ID
            limit: Maximum number to return

        Returns:
            List of snapshots
        """
        return await self.store.list_snapshots(session_id=session_id, limit=limit)

    def register_connector(self, connector: BaseConnector) -> None:
        """Register a connector with the tracker.

        Args:
            connector: Connector instance to register
        """
        self.registry.register_connector(connector)

    def get_connector(
        self, connector_type: str, connector_id: str
    ) -> Optional[BaseConnector]:
        """Get a registered connector.

        Args:
            connector_type: Type of connector
            connector_id: Connector ID

        Returns:
            The connector or None
        """
        return self.registry.get_connector(connector_type, connector_id)


def track_action(
    action_type: str,
    tracker: Optional[StateTracker] = None,
    connector: Optional[BaseConnector] = None,
    capture_args: bool = True,
    capture_result: bool = True,
):
    """Decorator for tracking function calls as actions.

    Args:
        action_type: Type identifier for the action
        tracker: Tracker instance (uses default if None)
        connector: Connector for state capture
        capture_args: Whether to capture function arguments
        capture_result: Whether to capture function result

    Returns:
        Decorated function
    """
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            nonlocal tracker
            if tracker is None:
                # Would use a global tracker in real usage
                raise ValueError("No tracker provided to @track_action")

            action_data = {}
            if capture_args:
                action_data["args"] = [str(a) for a in args]
                action_data["kwargs"] = {k: str(v) for k, v in kwargs.items()}

            before_state = None
            if connector:
                before_state = await connector.capture_state()

            try:
                result = await func(*args, **kwargs)
                action_data["status"] = "success"
                if capture_result:
                    action_data["result"] = str(result)
            except Exception as e:
                action_data["status"] = "error"
                action_data["error"] = str(e)
                raise
            finally:
                after_state = None
                if connector:
                    after_state = await connector.capture_state()

                await tracker.record_action(
                    action_type=action_type,
                    action_data=action_data,
                    before_state=before_state,
                    after_state=after_state,
                    connector_type=connector.connector_type if connector else None,
                    connector_id=connector.connector_id if connector else None,
                )

            return result

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            return asyncio.get_event_loop().run_until_complete(
                async_wrapper(*args, **kwargs)
            )

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
