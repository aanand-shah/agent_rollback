"""
Pydantic models for AgentRollback data structures.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
import uuid


def generate_id() -> str:
    """Generate a unique ID."""
    return str(uuid.uuid4())


class SessionStatus(str, Enum):
    """Status of a tracking session."""
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class SnapshotType(str, Enum):
    """Type of state snapshot."""
    BEFORE = "before"
    AFTER = "after"
    CHECKPOINT = "checkpoint"


class ActionStatus(str, Enum):
    """Status of an action."""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class SessionCreate(BaseModel):
    """Request model for creating a new session."""
    agent_id: str = Field(..., description="Identifier for the AI agent")
    metadata: Optional[dict[str, Any]] = Field(default=None, description="Additional session metadata")


class Session(BaseModel):
    """Represents an agent tracking session."""
    id: str = Field(default_factory=generate_id, description="Unique session identifier")
    agent_id: str = Field(..., description="Identifier for the AI agent")
    started_at: datetime = Field(default_factory=datetime.utcnow, description="Session start timestamp")
    ended_at: Optional[datetime] = Field(default=None, description="Session end timestamp")
    metadata: Optional[dict[str, Any]] = Field(default=None, description="Additional session metadata")
    status: SessionStatus = Field(default=SessionStatus.ACTIVE, description="Current session status")

    class Config:
        from_attributes = True


class SnapshotCreate(BaseModel):
    """Request model for creating a snapshot."""
    session_id: str = Field(..., description="Associated session ID")
    action_id: Optional[str] = Field(default=None, description="Associated action ID")
    connector_type: str = Field(..., description="Type of connector (database, filesystem, api, memory)")
    connector_id: Optional[str] = Field(default=None, description="Specific connector instance ID")
    state_data: dict[str, Any] = Field(..., description="The captured state data")
    snapshot_type: SnapshotType = Field(..., description="Type of snapshot (before, after, checkpoint)")


class Snapshot(BaseModel):
    """Represents a state snapshot at a point in time."""
    id: str = Field(default_factory=generate_id, description="Unique snapshot identifier")
    session_id: str = Field(..., description="Associated session ID")
    action_id: Optional[str] = Field(default=None, description="Associated action ID")
    connector_type: str = Field(..., description="Type of connector")
    connector_id: Optional[str] = Field(default=None, description="Specific connector instance ID")
    state_data: dict[str, Any] = Field(..., description="The captured state data")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Snapshot creation timestamp")
    snapshot_type: SnapshotType = Field(..., description="Type of snapshot")

    class Config:
        from_attributes = True


class ActionCreate(BaseModel):
    """Request model for recording an action."""
    session_id: str = Field(..., description="Associated session ID")
    action_type: str = Field(..., description="Type of action performed")
    action_data: Optional[dict[str, Any]] = Field(default=None, description="Action parameters and details")
    before_state: Optional[dict[str, Any]] = Field(default=None, description="State before action (for auto-snapshot)")
    after_state: Optional[dict[str, Any]] = Field(default=None, description="State after action (for auto-snapshot)")
    connector_type: Optional[str] = Field(default=None, description="Connector type for auto-snapshots")
    connector_id: Optional[str] = Field(default=None, description="Connector ID for auto-snapshots")
    parent_action_id: Optional[str] = Field(default=None, description="Parent action ID for nested operations")


class Action(BaseModel):
    """Represents an agent action with before/after snapshots."""
    id: str = Field(default_factory=generate_id, description="Unique action identifier")
    session_id: str = Field(..., description="Associated session ID")
    action_type: str = Field(..., description="Type of action performed")
    action_data: Optional[dict[str, Any]] = Field(default=None, description="Action parameters and details")
    before_snapshot_id: Optional[str] = Field(default=None, description="Snapshot ID before action")
    after_snapshot_id: Optional[str] = Field(default=None, description="Snapshot ID after action")
    executed_at: datetime = Field(default_factory=datetime.utcnow, description="Action execution timestamp")
    status: ActionStatus = Field(default=ActionStatus.COMPLETED, description="Action status")
    parent_action_id: Optional[str] = Field(default=None, description="Parent action ID for nested operations")

    class Config:
        from_attributes = True


class RollbackRequest(BaseModel):
    """Request model for executing a rollback."""
    session_id: str = Field(..., description="Session to rollback")
    target_snapshot_id: str = Field(..., description="Snapshot to restore to")
    dry_run: bool = Field(default=False, description="If true, only simulate the rollback")


class RollbackResult(BaseModel):
    """Result of a rollback operation."""
    success: bool = Field(..., description="Whether rollback succeeded")
    session_id: str = Field(..., description="Session that was rolled back")
    target_snapshot_id: str = Field(..., description="Snapshot that was restored")
    actions_reverted: int = Field(..., description="Number of actions reverted")
    errors: list[str] = Field(default_factory=list, description="Any errors encountered")
    dry_run: bool = Field(default=False, description="Whether this was a dry run")


class ReplayRequest(BaseModel):
    """Request model for replaying actions."""
    session_id: str = Field(..., description="Session to replay from")
    from_snapshot_id: str = Field(..., description="Starting snapshot")
    to_snapshot_id: Optional[str] = Field(default=None, description="Ending snapshot (None for latest)")
    dry_run: bool = Field(default=False, description="If true, only simulate the replay")


class ReplayResult(BaseModel):
    """Result of a replay operation."""
    success: bool = Field(..., description="Whether replay succeeded")
    session_id: str = Field(..., description="Session that was replayed")
    actions_replayed: int = Field(..., description="Number of actions replayed")
    new_session_id: Optional[str] = Field(default=None, description="New session created for replay")
    errors: list[str] = Field(default_factory=list, description="Any errors encountered")
    dry_run: bool = Field(default=False, description="Whether this was a dry run")


class DiffChange(BaseModel):
    """Represents a single change between two states."""
    path: str = Field(..., description="JSON path to the changed value")
    operation: str = Field(..., description="Type of change: add, remove, modify")
    old_value: Optional[Any] = Field(default=None, description="Previous value")
    new_value: Optional[Any] = Field(default=None, description="New value")


class DiffResult(BaseModel):
    """Result of comparing two snapshots."""
    snapshot_a_id: str = Field(..., description="First snapshot ID")
    snapshot_b_id: str = Field(..., description="Second snapshot ID")
    changes: list[DiffChange] = Field(default_factory=list, description="List of changes")
    summary: str = Field(default="", description="Human-readable summary of changes")


class ConnectorInfo(BaseModel):
    """Information about a registered connector."""
    connector_type: str = Field(..., description="Type identifier for the connector")
    connector_id: str = Field(..., description="Unique instance identifier")
    config: Optional[dict[str, Any]] = Field(default=None, description="Connector configuration")
    registered_at: datetime = Field(default_factory=datetime.utcnow, description="Registration timestamp")


class TimelineEntry(BaseModel):
    """An entry in the session timeline."""
    timestamp: datetime = Field(..., description="When the event occurred")
    event_type: str = Field(..., description="Type of event (action, snapshot, checkpoint)")
    action: Optional[Action] = Field(default=None, description="Action details if applicable")
    snapshot: Optional[Snapshot] = Field(default=None, description="Snapshot details if applicable")


class SessionTimeline(BaseModel):
    """Complete timeline for a session."""
    session: Session = Field(..., description="Session information")
    entries: list[TimelineEntry] = Field(default_factory=list, description="Timeline entries")
    total_actions: int = Field(default=0, description="Total number of actions")
    total_snapshots: int = Field(default=0, description="Total number of snapshots")
