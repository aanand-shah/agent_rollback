"""
SQLite storage layer for AgentRollback.

Provides async database operations for sessions, snapshots, and actions.
"""

import json
import aiosqlite
from datetime import datetime
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

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
    ConnectorInfo,
    generate_id,
)


class StateStore:
    """SQLite-backed storage for agent state tracking."""

    def __init__(self, db_path: str = "agent_rollback.db"):
        """Initialize the state store.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None

    async def initialize(self) -> None:
        """Initialize the database schema."""
        migrations_path = Path(__file__).parent / "migrations" / "init.sql"
        async with self._get_connection() as conn:
            with open(migrations_path, "r") as f:
                await conn.executescript(f.read())
            await conn.commit()

    @asynccontextmanager
    async def _get_connection(self):
        """Get a database connection."""
        conn = await aiosqlite.connect(self.db_path)
        conn.row_factory = aiosqlite.Row
        try:
            yield conn
        finally:
            await conn.close()

    async def connect(self) -> None:
        """Establish persistent connection."""
        if self._connection is None:
            self._connection = await aiosqlite.connect(self.db_path)
            self._connection.row_factory = aiosqlite.Row

    async def close(self) -> None:
        """Close persistent connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None

    # Session operations

    async def create_session(self, session_create: SessionCreate) -> Session:
        """Create a new tracking session."""
        session = Session(
            id=generate_id(),
            agent_id=session_create.agent_id,
            metadata=session_create.metadata,
        )
        async with self._get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO sessions (id, agent_id, started_at, metadata, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session.id,
                    session.agent_id,
                    session.started_at.isoformat(),
                    json.dumps(session.metadata) if session.metadata else None,
                    session.status.value,
                ),
            )
            await conn.commit()
        return session

    async def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID."""
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            )
            row = await cursor.fetchone()
            if row:
                return self._row_to_session(row)
        return None

    async def list_sessions(
        self,
        status: Optional[SessionStatus] = None,
        agent_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Session]:
        """List sessions with optional filtering."""
        query = "SELECT * FROM sessions WHERE 1=1"
        params: list = []

        if status:
            query += " AND status = ?"
            params.append(status.value)
        if agent_id:
            query += " AND agent_id = ?"
            params.append(agent_id)

        query += " ORDER BY started_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        async with self._get_connection() as conn:
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            return [self._row_to_session(row) for row in rows]

    async def update_session(
        self,
        session_id: str,
        status: Optional[SessionStatus] = None,
        ended_at: Optional[datetime] = None,
        metadata: Optional[dict] = None,
    ) -> Optional[Session]:
        """Update a session."""
        updates = []
        params = []

        if status is not None:
            updates.append("status = ?")
            params.append(status.value)
        if ended_at is not None:
            updates.append("ended_at = ?")
            params.append(ended_at.isoformat())
        if metadata is not None:
            updates.append("metadata = ?")
            params.append(json.dumps(metadata))

        if not updates:
            return await self.get_session(session_id)

        params.append(session_id)
        async with self._get_connection() as conn:
            await conn.execute(
                f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            await conn.commit()

        return await self.get_session(session_id)

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session and all related data."""
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM sessions WHERE id = ?", (session_id,)
            )
            await conn.commit()
            return cursor.rowcount > 0

    def _row_to_session(self, row: aiosqlite.Row) -> Session:
        """Convert a database row to a Session object."""
        return Session(
            id=row["id"],
            agent_id=row["agent_id"],
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else datetime.utcnow(),
            ended_at=datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None,
            metadata=json.loads(row["metadata"]) if row["metadata"] else None,
            status=SessionStatus(row["status"]),
        )

    # Snapshot operations

    async def create_snapshot(self, snapshot_create: SnapshotCreate) -> Snapshot:
        """Create a new state snapshot."""
        snapshot = Snapshot(
            id=generate_id(),
            session_id=snapshot_create.session_id,
            action_id=snapshot_create.action_id,
            connector_type=snapshot_create.connector_type,
            connector_id=snapshot_create.connector_id,
            state_data=snapshot_create.state_data,
            snapshot_type=snapshot_create.snapshot_type,
        )
        async with self._get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO snapshots
                (id, session_id, action_id, connector_type, connector_id, state_data, created_at, snapshot_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.id,
                    snapshot.session_id,
                    snapshot.action_id,
                    snapshot.connector_type,
                    snapshot.connector_id,
                    json.dumps(snapshot.state_data),
                    snapshot.created_at.isoformat(),
                    snapshot.snapshot_type.value,
                ),
            )
            await conn.commit()
        return snapshot

    async def get_snapshot(self, snapshot_id: str) -> Optional[Snapshot]:
        """Get a snapshot by ID."""
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM snapshots WHERE id = ?", (snapshot_id,)
            )
            row = await cursor.fetchone()
            if row:
                return self._row_to_snapshot(row)
        return None

    async def list_snapshots(
        self,
        session_id: Optional[str] = None,
        action_id: Optional[str] = None,
        snapshot_type: Optional[SnapshotType] = None,
        connector_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Snapshot]:
        """List snapshots with optional filtering."""
        query = "SELECT * FROM snapshots WHERE 1=1"
        params: list = []

        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)
        if action_id:
            query += " AND action_id = ?"
            params.append(action_id)
        if snapshot_type:
            query += " AND snapshot_type = ?"
            params.append(snapshot_type.value)
        if connector_type:
            query += " AND connector_type = ?"
            params.append(connector_type)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        async with self._get_connection() as conn:
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            return [self._row_to_snapshot(row) for row in rows]

    async def get_latest_snapshot(
        self,
        session_id: str,
        connector_type: Optional[str] = None,
        connector_id: Optional[str] = None,
    ) -> Optional[Snapshot]:
        """Get the most recent snapshot for a session."""
        query = "SELECT * FROM snapshots WHERE session_id = ?"
        params: list = [session_id]

        if connector_type:
            query += " AND connector_type = ?"
            params.append(connector_type)
        if connector_id:
            query += " AND connector_id = ?"
            params.append(connector_id)

        query += " ORDER BY created_at DESC LIMIT 1"

        async with self._get_connection() as conn:
            cursor = await conn.execute(query, params)
            row = await cursor.fetchone()
            if row:
                return self._row_to_snapshot(row)
        return None

    def _row_to_snapshot(self, row: aiosqlite.Row) -> Snapshot:
        """Convert a database row to a Snapshot object."""
        return Snapshot(
            id=row["id"],
            session_id=row["session_id"],
            action_id=row["action_id"],
            connector_type=row["connector_type"],
            connector_id=row["connector_id"],
            state_data=json.loads(row["state_data"]) if row["state_data"] else {},
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.utcnow(),
            snapshot_type=SnapshotType(row["snapshot_type"]),
        )

    # Action operations

    async def create_action(self, action_create: ActionCreate) -> Action:
        """Create a new action record."""
        action_id = generate_id()
        before_snapshot_id = None
        after_snapshot_id = None

        # Create before snapshot if state provided
        if action_create.before_state is not None:
            before_snapshot = await self.create_snapshot(
                SnapshotCreate(
                    session_id=action_create.session_id,
                    action_id=action_id,
                    connector_type=action_create.connector_type or "unknown",
                    connector_id=action_create.connector_id,
                    state_data=action_create.before_state,
                    snapshot_type=SnapshotType.BEFORE,
                )
            )
            before_snapshot_id = before_snapshot.id

        # Create after snapshot if state provided
        if action_create.after_state is not None:
            after_snapshot = await self.create_snapshot(
                SnapshotCreate(
                    session_id=action_create.session_id,
                    action_id=action_id,
                    connector_type=action_create.connector_type or "unknown",
                    connector_id=action_create.connector_id,
                    state_data=action_create.after_state,
                    snapshot_type=SnapshotType.AFTER,
                )
            )
            after_snapshot_id = after_snapshot.id

        action = Action(
            id=action_id,
            session_id=action_create.session_id,
            action_type=action_create.action_type,
            action_data=action_create.action_data,
            before_snapshot_id=before_snapshot_id,
            after_snapshot_id=after_snapshot_id,
            parent_action_id=action_create.parent_action_id,
        )

        async with self._get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO actions
                (id, session_id, action_type, action_data, before_snapshot_id, after_snapshot_id,
                 executed_at, status, parent_action_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    action.id,
                    action.session_id,
                    action.action_type,
                    json.dumps(action.action_data) if action.action_data else None,
                    action.before_snapshot_id,
                    action.after_snapshot_id,
                    action.executed_at.isoformat(),
                    action.status.value,
                    action.parent_action_id,
                ),
            )
            await conn.commit()

        return action

    async def get_action(self, action_id: str) -> Optional[Action]:
        """Get an action by ID."""
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM actions WHERE id = ?", (action_id,)
            )
            row = await cursor.fetchone()
            if row:
                return self._row_to_action(row)
        return None

    async def list_actions(
        self,
        session_id: Optional[str] = None,
        status: Optional[ActionStatus] = None,
        action_type: Optional[str] = None,
        parent_action_id: Optional[str] = None,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Action]:
        """List actions with optional filtering."""
        query = "SELECT * FROM actions WHERE 1=1"
        params: list = []

        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)
        if status:
            query += " AND status = ?"
            params.append(status.value)
        if action_type:
            query += " AND action_type = ?"
            params.append(action_type)
        if parent_action_id:
            query += " AND parent_action_id = ?"
            params.append(parent_action_id)
        if from_time:
            query += " AND executed_at >= ?"
            params.append(from_time.isoformat())
        if to_time:
            query += " AND executed_at <= ?"
            params.append(to_time.isoformat())

        query += " ORDER BY executed_at ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        async with self._get_connection() as conn:
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            return [self._row_to_action(row) for row in rows]

    async def update_action(
        self,
        action_id: str,
        status: Optional[ActionStatus] = None,
        after_snapshot_id: Optional[str] = None,
    ) -> Optional[Action]:
        """Update an action."""
        updates = []
        params = []

        if status is not None:
            updates.append("status = ?")
            params.append(status.value)
        if after_snapshot_id is not None:
            updates.append("after_snapshot_id = ?")
            params.append(after_snapshot_id)

        if not updates:
            return await self.get_action(action_id)

        params.append(action_id)
        async with self._get_connection() as conn:
            await conn.execute(
                f"UPDATE actions SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            await conn.commit()

        return await self.get_action(action_id)

    async def get_actions_after_snapshot(
        self, session_id: str, snapshot_id: str
    ) -> list[Action]:
        """Get all actions that occurred after a given snapshot."""
        snapshot = await self.get_snapshot(snapshot_id)
        if not snapshot:
            return []

        return await self.list_actions(
            session_id=session_id,
            from_time=snapshot.created_at,
            limit=1000,
        )

    def _row_to_action(self, row: aiosqlite.Row) -> Action:
        """Convert a database row to an Action object."""
        return Action(
            id=row["id"],
            session_id=row["session_id"],
            action_type=row["action_type"],
            action_data=json.loads(row["action_data"]) if row["action_data"] else None,
            before_snapshot_id=row["before_snapshot_id"],
            after_snapshot_id=row["after_snapshot_id"],
            executed_at=datetime.fromisoformat(row["executed_at"]) if row["executed_at"] else datetime.utcnow(),
            status=ActionStatus(row["status"]),
            parent_action_id=row["parent_action_id"],
        )

    # Connector operations

    async def register_connector(self, connector_info: ConnectorInfo) -> ConnectorInfo:
        """Register a connector."""
        async with self._get_connection() as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO connectors (connector_type, connector_id, config, registered_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    connector_info.connector_type,
                    connector_info.connector_id,
                    json.dumps(connector_info.config) if connector_info.config else None,
                    connector_info.registered_at.isoformat(),
                ),
            )
            await conn.commit()
        return connector_info

    async def get_connector(
        self, connector_type: str, connector_id: str
    ) -> Optional[ConnectorInfo]:
        """Get a registered connector."""
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM connectors WHERE connector_type = ? AND connector_id = ?",
                (connector_type, connector_id),
            )
            row = await cursor.fetchone()
            if row:
                return ConnectorInfo(
                    connector_type=row["connector_type"],
                    connector_id=row["connector_id"],
                    config=json.loads(row["config"]) if row["config"] else None,
                    registered_at=datetime.fromisoformat(row["registered_at"]) if row["registered_at"] else datetime.utcnow(),
                )
        return None

    async def list_connectors(
        self, connector_type: Optional[str] = None
    ) -> list[ConnectorInfo]:
        """List all registered connectors."""
        query = "SELECT * FROM connectors"
        params: list = []

        if connector_type:
            query += " WHERE connector_type = ?"
            params.append(connector_type)

        query += " ORDER BY registered_at DESC"

        async with self._get_connection() as conn:
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            return [
                ConnectorInfo(
                    connector_type=row["connector_type"],
                    connector_id=row["connector_id"],
                    config=json.loads(row["config"]) if row["config"] else None,
                    registered_at=datetime.fromisoformat(row["registered_at"]) if row["registered_at"] else datetime.utcnow(),
                )
                for row in rows
            ]

    async def unregister_connector(
        self, connector_type: str, connector_id: str
    ) -> bool:
        """Unregister a connector."""
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM connectors WHERE connector_type = ? AND connector_id = ?",
                (connector_type, connector_id),
            )
            await conn.commit()
            return cursor.rowcount > 0
