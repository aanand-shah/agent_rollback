"""
AgentRollback - AI Agent State Recovery System

A middleware layer that captures state snapshots before/after each agent action,
enabling point-in-time recovery for AI agents.
"""

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
    RollbackRequest,
    ReplayRequest,
    DiffResult,
)
from agent_rollback.tracker import StateTracker
from agent_rollback.store import StateStore
from agent_rollback.recovery import RecoveryEngine
from agent_rollback.sdk import AgentRollbackClient, track_action

__version__ = "0.1.0"
__all__ = [
    # Models
    "Session",
    "SessionCreate",
    "SessionStatus",
    "Snapshot",
    "SnapshotCreate",
    "SnapshotType",
    "Action",
    "ActionCreate",
    "ActionStatus",
    "RollbackRequest",
    "ReplayRequest",
    "DiffResult",
    # Core components
    "StateTracker",
    "StateStore",
    "RecoveryEngine",
    # SDK
    "AgentRollbackClient",
    "track_action",
]
