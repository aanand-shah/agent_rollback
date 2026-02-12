"""
Recovery engine for rollback, replay, and state restoration.
"""

from datetime import datetime
from typing import Any, Optional

from agent_rollback.models import (
    Session,
    SessionStatus,
    Snapshot,
    Action,
    ActionStatus,
    RollbackRequest,
    RollbackResult,
    ReplayRequest,
    ReplayResult,
    DiffResult,
)
from agent_rollback.store import StateStore
from agent_rollback.connectors.base import BaseConnector, ConnectorRegistry, get_registry
from agent_rollback.utils.diff import compute_diff, summarize_diff, create_diff_result


class RecoveryEngine:
    """Engine for performing state recovery operations.

    Provides rollback, replay, and diff functionality using stored
    snapshots and registered connectors.
    """

    def __init__(
        self,
        store: StateStore,
        registry: Optional[ConnectorRegistry] = None,
    ):
        """Initialize the recovery engine.

        Args:
            store: State store for accessing snapshots and actions
            registry: Connector registry (uses global if None)
        """
        self.store = store
        self.registry = registry or get_registry()

    async def rollback(self, request: RollbackRequest) -> RollbackResult:
        """Rollback a session to a specific snapshot.

        This restores the state captured in the target snapshot by:
        1. Finding the connector associated with the snapshot
        2. Calling the connector's restore_state method
        3. Marking affected actions as rolled back

        Args:
            request: Rollback request parameters

        Returns:
            Result of the rollback operation
        """
        errors = []
        actions_reverted = 0

        # Get the target snapshot
        target_snapshot = await self.store.get_snapshot(request.target_snapshot_id)
        if not target_snapshot:
            return RollbackResult(
                success=False,
                session_id=request.session_id,
                target_snapshot_id=request.target_snapshot_id,
                actions_reverted=0,
                errors=["Target snapshot not found"],
                dry_run=request.dry_run,
            )

        # Get the session
        session = await self.store.get_session(request.session_id)
        if not session:
            return RollbackResult(
                success=False,
                session_id=request.session_id,
                target_snapshot_id=request.target_snapshot_id,
                actions_reverted=0,
                errors=["Session not found"],
                dry_run=request.dry_run,
            )

        # Find actions that occurred after the target snapshot
        actions_to_revert = await self._get_actions_after_snapshot(
            request.session_id, target_snapshot
        )
        actions_reverted = len(actions_to_revert)

        if request.dry_run:
            return RollbackResult(
                success=True,
                session_id=request.session_id,
                target_snapshot_id=request.target_snapshot_id,
                actions_reverted=actions_reverted,
                errors=[],
                dry_run=True,
            )

        # Get the connector for state restoration
        connector = self.registry.get_connector(
            target_snapshot.connector_type,
            target_snapshot.connector_id or "",
        )

        if connector:
            # Validate the state can be restored
            if not await connector.validate_state(target_snapshot.state_data):
                errors.append(
                    f"State validation failed for connector {target_snapshot.connector_type}"
                )
            else:
                # Restore the state
                success = await connector.restore_state(target_snapshot.state_data)
                if not success:
                    errors.append(
                        f"State restoration failed for connector {target_snapshot.connector_type}"
                    )
        # No connector registered - that's OK, rollback still succeeds
        # The caller (e.g., dashboard) can use the snapshot data to restore state externally

        # Mark actions as rolled back
        for action in actions_to_revert:
            await self.store.update_action(action.id, status=ActionStatus.ROLLED_BACK)

        # Update session status
        await self.store.update_session(
            request.session_id,
            status=SessionStatus.ROLLED_BACK,
        )

        return RollbackResult(
            success=len(errors) == 0,
            session_id=request.session_id,
            target_snapshot_id=request.target_snapshot_id,
            actions_reverted=actions_reverted,
            errors=errors,
            dry_run=False,
        )

    async def replay(self, request: ReplayRequest) -> ReplayResult:
        """Replay actions from a snapshot.

        This re-executes actions that occurred after the from_snapshot,
        optionally stopping at to_snapshot.

        Note: Actual replay requires action-specific logic. This method
        creates a new session and records the replay attempt.

        Args:
            request: Replay request parameters

        Returns:
            Result of the replay operation
        """
        errors = []

        # Get the starting snapshot
        from_snapshot = await self.store.get_snapshot(request.from_snapshot_id)
        if not from_snapshot:
            return ReplayResult(
                success=False,
                session_id=request.session_id,
                actions_replayed=0,
                errors=["From snapshot not found"],
                dry_run=request.dry_run,
            )

        # Get actions to replay
        actions_to_replay = await self._get_actions_after_snapshot(
            request.session_id, from_snapshot
        )

        # If to_snapshot specified, filter actions
        if request.to_snapshot_id:
            to_snapshot = await self.store.get_snapshot(request.to_snapshot_id)
            if to_snapshot:
                actions_to_replay = [
                    a
                    for a in actions_to_replay
                    if a.executed_at <= to_snapshot.created_at
                ]

        if request.dry_run:
            return ReplayResult(
                success=True,
                session_id=request.session_id,
                actions_replayed=len(actions_to_replay),
                errors=[],
                dry_run=True,
            )

        # Get the original session for agent ID
        original_session = await self.store.get_session(request.session_id)
        if not original_session:
            return ReplayResult(
                success=False,
                session_id=request.session_id,
                actions_replayed=0,
                errors=["Original session not found"],
                dry_run=False,
            )

        # Create a new session for the replay
        from agent_rollback.models import SessionCreate
        new_session = await self.store.create_session(
            SessionCreate(
                agent_id=original_session.agent_id,
                metadata={
                    "replay_of": request.session_id,
                    "from_snapshot": request.from_snapshot_id,
                    "to_snapshot": request.to_snapshot_id,
                },
            )
        )

        # First restore to the starting state
        connector = self.registry.get_connector(
            from_snapshot.connector_type,
            from_snapshot.connector_id or "",
        )

        if connector:
            success = await connector.restore_state(from_snapshot.state_data)
            if not success:
                errors.append("Failed to restore starting state")

        # Record each action in the new session
        # Note: Actual re-execution would require action-specific logic
        replayed_count = 0
        for action in actions_to_replay:
            from agent_rollback.models import ActionCreate
            await self.store.create_action(
                ActionCreate(
                    session_id=new_session.id,
                    action_type=action.action_type,
                    action_data={
                        **(action.action_data or {}),
                        "replayed_from": action.id,
                    },
                    parent_action_id=action.parent_action_id,
                )
            )
            replayed_count += 1

        return ReplayResult(
            success=len(errors) == 0,
            session_id=request.session_id,
            actions_replayed=replayed_count,
            new_session_id=new_session.id,
            errors=errors,
            dry_run=False,
        )

    async def diff(
        self,
        snapshot_a_id: str,
        snapshot_b_id: str,
    ) -> DiffResult:
        """Compare two snapshots and return differences.

        Args:
            snapshot_a_id: ID of first snapshot
            snapshot_b_id: ID of second snapshot

        Returns:
            DiffResult with list of changes
        """
        snapshot_a = await self.store.get_snapshot(snapshot_a_id)
        snapshot_b = await self.store.get_snapshot(snapshot_b_id)

        if not snapshot_a or not snapshot_b:
            return DiffResult(
                snapshot_a_id=snapshot_a_id,
                snapshot_b_id=snapshot_b_id,
                changes=[],
                summary="One or both snapshots not found",
            )

        return create_diff_result(
            snapshot_a_id=snapshot_a_id,
            snapshot_b_id=snapshot_b_id,
            state_a=snapshot_a.state_data,
            state_b=snapshot_b.state_data,
        )

    async def diff_session_states(
        self,
        session_id: str,
        connector_type: Optional[str] = None,
    ) -> DiffResult:
        """Compare first and last snapshots in a session.

        Args:
            session_id: Session to compare
            connector_type: Optional filter by connector type

        Returns:
            DiffResult comparing first and last snapshots
        """
        snapshots = await self.store.list_snapshots(
            session_id=session_id,
            connector_type=connector_type,
            limit=1000,
        )

        if len(snapshots) < 2:
            return DiffResult(
                snapshot_a_id="",
                snapshot_b_id="",
                changes=[],
                summary="Not enough snapshots to compare",
            )

        # Sort by creation time
        snapshots.sort(key=lambda s: s.created_at)
        first = snapshots[0]
        last = snapshots[-1]

        return create_diff_result(
            snapshot_a_id=first.id,
            snapshot_b_id=last.id,
            state_a=first.state_data,
            state_b=last.state_data,
        )

    async def get_rollback_preview(
        self,
        session_id: str,
        target_snapshot_id: str,
    ) -> dict[str, Any]:
        """Preview what a rollback would do without executing it.

        Args:
            session_id: Session to rollback
            target_snapshot_id: Target snapshot

        Returns:
            Dictionary with preview information
        """
        target_snapshot = await self.store.get_snapshot(target_snapshot_id)
        if not target_snapshot:
            return {"error": "Snapshot not found"}

        actions_to_revert = await self._get_actions_after_snapshot(
            session_id, target_snapshot
        )

        # Get current state for comparison
        current_snapshot = await self.store.get_latest_snapshot(
            session_id,
            connector_type=target_snapshot.connector_type,
            connector_id=target_snapshot.connector_id,
        )

        diff = None
        if current_snapshot:
            diff = create_diff_result(
                snapshot_a_id=current_snapshot.id,
                snapshot_b_id=target_snapshot_id,
                state_a=current_snapshot.state_data,
                state_b=target_snapshot.state_data,
            )

        return {
            "session_id": session_id,
            "target_snapshot_id": target_snapshot_id,
            "target_snapshot_time": target_snapshot.created_at.isoformat(),
            "actions_to_revert": len(actions_to_revert),
            "action_types": list(set(a.action_type for a in actions_to_revert)),
            "state_diff": diff.model_dump() if diff else None,
        }

    async def _get_actions_after_snapshot(
        self, session_id: str, snapshot: Snapshot
    ) -> list[Action]:
        """Get all actions that occurred after a snapshot.

        Args:
            session_id: Session ID
            snapshot: Reference snapshot

        Returns:
            List of actions after the snapshot
        """
        all_actions = await self.store.list_actions(
            session_id=session_id,
            limit=10000,
        )

        return [a for a in all_actions if a.executed_at > snapshot.created_at]

    async def find_checkpoint_before(
        self,
        session_id: str,
        timestamp: datetime,
        connector_type: Optional[str] = None,
    ) -> Optional[Snapshot]:
        """Find the most recent checkpoint before a given time.

        Args:
            session_id: Session to search
            timestamp: Reference timestamp
            connector_type: Optional connector filter

        Returns:
            The checkpoint snapshot, or None
        """
        from agent_rollback.models import SnapshotType

        snapshots = await self.store.list_snapshots(
            session_id=session_id,
            snapshot_type=SnapshotType.CHECKPOINT,
            connector_type=connector_type,
            limit=1000,
        )

        # Filter to before timestamp and sort descending
        candidates = [s for s in snapshots if s.created_at < timestamp]
        if not candidates:
            return None

        candidates.sort(key=lambda s: s.created_at, reverse=True)
        return candidates[0]

    async def list_recovery_points(
        self,
        session_id: str,
        include_checkpoints: bool = True,
        include_before_snapshots: bool = True,
    ) -> list[dict[str, Any]]:
        """List all possible recovery points for a session.

        Args:
            session_id: Session ID
            include_checkpoints: Include checkpoint snapshots
            include_before_snapshots: Include before-action snapshots

        Returns:
            List of recovery point info dictionaries
        """
        from agent_rollback.models import SnapshotType

        snapshots = await self.store.list_snapshots(
            session_id=session_id,
            limit=1000,
        )

        recovery_points = []
        for snapshot in snapshots:
            if snapshot.snapshot_type == SnapshotType.CHECKPOINT and include_checkpoints:
                recovery_points.append({
                    "snapshot_id": snapshot.id,
                    "type": "checkpoint",
                    "timestamp": snapshot.created_at.isoformat(),
                    "connector_type": snapshot.connector_type,
                    "connector_id": snapshot.connector_id,
                })
            elif snapshot.snapshot_type == SnapshotType.BEFORE and include_before_snapshots:
                recovery_points.append({
                    "snapshot_id": snapshot.id,
                    "type": "before_action",
                    "timestamp": snapshot.created_at.isoformat(),
                    "action_id": snapshot.action_id,
                    "connector_type": snapshot.connector_type,
                    "connector_id": snapshot.connector_id,
                })

        # Sort by timestamp
        recovery_points.sort(key=lambda p: p["timestamp"])
        return recovery_points
