"""
FastAPI REST server for AgentRollback.

Provides webhook endpoints for agent integration and dashboard APIs.
"""

from contextlib import asynccontextmanager
from typing import Any, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query, Path
from pydantic import BaseModel, Field

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
    RollbackResult,
    ReplayRequest,
    ReplayResult,
    DiffResult,
    SessionTimeline,
    TimelineEntry,
)
from agent_rollback.store import StateStore
from agent_rollback.tracker import StateTracker
from agent_rollback.recovery import RecoveryEngine


# Global instances
_store: Optional[StateStore] = None
_tracker: Optional[StateTracker] = None
_recovery: Optional[RecoveryEngine] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan manager for FastAPI app."""
    global _store, _tracker, _recovery

    # Initialize on startup
    _store = StateStore()
    await _store.initialize()
    _tracker = StateTracker(store=_store)
    _recovery = RecoveryEngine(store=_store)

    yield

    # Cleanup on shutdown
    await _store.close()


app = FastAPI(
    title="AgentRollback API",
    description="AI Agent State Recovery System - Git for AI Agents",
    version="0.1.0",
    lifespan=lifespan,
)


def get_store() -> StateStore:
    """Get the state store instance."""
    if _store is None:
        raise HTTPException(status_code=500, detail="Store not initialized")
    return _store


def get_tracker() -> StateTracker:
    """Get the tracker instance."""
    if _tracker is None:
        raise HTTPException(status_code=500, detail="Tracker not initialized")
    return _tracker


def get_recovery() -> RecoveryEngine:
    """Get the recovery engine instance."""
    if _recovery is None:
        raise HTTPException(status_code=500, detail="Recovery engine not initialized")
    return _recovery


# Response models

class SessionResponse(BaseModel):
    """Response model for session operations."""
    session: Session
    message: str = ""


class SessionListResponse(BaseModel):
    """Response model for listing sessions."""
    sessions: list[Session]
    total: int


class ActionResponse(BaseModel):
    """Response model for action operations."""
    action: Action
    before_snapshot: Optional[Snapshot] = None
    after_snapshot: Optional[Snapshot] = None
    message: str = ""


class ActionListResponse(BaseModel):
    """Response model for listing actions."""
    actions: list[Action]
    total: int


class SnapshotResponse(BaseModel):
    """Response model for snapshot operations."""
    snapshot: Snapshot
    message: str = ""


class SnapshotListResponse(BaseModel):
    """Response model for listing snapshots."""
    snapshots: list[Snapshot]
    total: int


class CheckpointRequest(BaseModel):
    """Request model for creating a checkpoint."""
    connector_type: str = Field(default="manual", description="Type of connector")
    connector_id: Optional[str] = Field(default=None, description="Connector instance ID")
    state_data: Optional[dict[str, Any]] = Field(default=None, description="State data to checkpoint")


class DiffRequest(BaseModel):
    """Request model for diff operation."""
    snapshot_a_id: str = Field(..., description="First snapshot ID")
    snapshot_b_id: str = Field(..., description="Second snapshot ID")


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    timestamp: str


# Health endpoint

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        version="0.1.0",
        timestamp=datetime.utcnow().isoformat(),
    )


# Session endpoints

@app.post("/api/v1/sessions", response_model=SessionResponse, tags=["Sessions"])
async def create_session(session_create: SessionCreate):
    """Create a new tracking session."""
    store = get_store()
    session = await store.create_session(session_create)
    return SessionResponse(session=session, message="Session created successfully")


@app.get("/api/v1/sessions", response_model=SessionListResponse, tags=["Sessions"])
async def list_sessions(
    status: Optional[SessionStatus] = Query(default=None, description="Filter by status"),
    agent_id: Optional[str] = Query(default=None, description="Filter by agent ID"),
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
):
    """List all sessions with optional filtering."""
    store = get_store()
    sessions = await store.list_sessions(
        status=status,
        agent_id=agent_id,
        limit=limit,
        offset=offset,
    )
    return SessionListResponse(sessions=sessions, total=len(sessions))


@app.get("/api/v1/sessions/{session_id}", response_model=SessionResponse, tags=["Sessions"])
async def get_session(session_id: str = Path(..., description="Session ID")):
    """Get session details."""
    store = get_store()
    session = await store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionResponse(session=session)


@app.delete("/api/v1/sessions/{session_id}", response_model=SessionResponse, tags=["Sessions"])
async def end_session(
    session_id: str = Path(..., description="Session ID"),
    status: SessionStatus = Query(default=SessionStatus.COMPLETED, description="Final status"),
):
    """End a session."""
    store = get_store()
    session = await store.update_session(
        session_id,
        status=status,
        ended_at=datetime.utcnow(),
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionResponse(session=session, message="Session ended")


@app.get("/api/v1/sessions/{session_id}/timeline", response_model=SessionTimeline, tags=["Sessions"])
async def get_session_timeline(session_id: str = Path(..., description="Session ID")):
    """Get the complete timeline for a session."""
    store = get_store()

    session = await store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    actions = await store.list_actions(session_id=session_id, limit=1000)
    snapshots = await store.list_snapshots(session_id=session_id, limit=1000)

    entries = []

    for action in actions:
        entries.append(
            TimelineEntry(
                timestamp=action.executed_at,
                event_type="action",
                action=action,
            )
        )

    for snapshot in snapshots:
        if snapshot.snapshot_type == SnapshotType.CHECKPOINT:
            entries.append(
                TimelineEntry(
                    timestamp=snapshot.created_at,
                    event_type="checkpoint",
                    snapshot=snapshot,
                )
            )

    entries.sort(key=lambda e: e.timestamp)

    return SessionTimeline(
        session=session,
        entries=entries,
        total_actions=len(actions),
        total_snapshots=len(snapshots),
    )


# Action endpoints

@app.post("/api/v1/sessions/{session_id}/actions", response_model=ActionResponse, tags=["Actions"])
async def record_action(
    session_id: str = Path(..., description="Session ID"),
    action_create: ActionCreate = ...,
):
    """Record an action in a session."""
    store = get_store()

    # Verify session exists
    session = await store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Override session_id from path
    action_create.session_id = session_id

    action = await store.create_action(action_create)

    # Get associated snapshots
    before_snapshot = None
    after_snapshot = None
    if action.before_snapshot_id:
        before_snapshot = await store.get_snapshot(action.before_snapshot_id)
    if action.after_snapshot_id:
        after_snapshot = await store.get_snapshot(action.after_snapshot_id)

    return ActionResponse(
        action=action,
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        message="Action recorded",
    )


@app.get("/api/v1/sessions/{session_id}/actions", response_model=ActionListResponse, tags=["Actions"])
async def list_session_actions(
    session_id: str = Path(..., description="Session ID"),
    status: Optional[ActionStatus] = Query(default=None, description="Filter by status"),
    action_type: Optional[str] = Query(default=None, description="Filter by action type"),
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
):
    """List actions in a session."""
    store = get_store()
    actions = await store.list_actions(
        session_id=session_id,
        status=status,
        action_type=action_type,
        limit=limit,
        offset=offset,
    )
    return ActionListResponse(actions=actions, total=len(actions))


# Checkpoint endpoints

@app.post("/api/v1/sessions/{session_id}/checkpoint", response_model=SnapshotResponse, tags=["Checkpoints"])
async def create_checkpoint(
    session_id: str = Path(..., description="Session ID"),
    checkpoint: CheckpointRequest = ...,
):
    """Create a manual checkpoint in a session."""
    store = get_store()

    # Verify session exists
    session = await store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    snapshot = await store.create_snapshot(
        SnapshotCreate(
            session_id=session_id,
            connector_type=checkpoint.connector_type,
            connector_id=checkpoint.connector_id,
            state_data=checkpoint.state_data or {"checkpoint": True},
            snapshot_type=SnapshotType.CHECKPOINT,
        )
    )

    return SnapshotResponse(snapshot=snapshot, message="Checkpoint created")


# Snapshot endpoints

@app.get("/api/v1/snapshots/{snapshot_id}", response_model=SnapshotResponse, tags=["Snapshots"])
async def get_snapshot(snapshot_id: str = Path(..., description="Snapshot ID")):
    """Get snapshot details."""
    store = get_store()
    snapshot = await store.get_snapshot(snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return SnapshotResponse(snapshot=snapshot)


@app.get("/api/v1/sessions/{session_id}/snapshots", response_model=SnapshotListResponse, tags=["Snapshots"])
async def list_session_snapshots(
    session_id: str = Path(..., description="Session ID"),
    snapshot_type: Optional[SnapshotType] = Query(default=None, description="Filter by type"),
    connector_type: Optional[str] = Query(default=None, description="Filter by connector type"),
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
):
    """List snapshots in a session."""
    store = get_store()
    snapshots = await store.list_snapshots(
        session_id=session_id,
        snapshot_type=snapshot_type,
        connector_type=connector_type,
        limit=limit,
        offset=offset,
    )
    return SnapshotListResponse(snapshots=snapshots, total=len(snapshots))


# Diff endpoints

@app.get("/api/v1/diff", response_model=DiffResult, tags=["Recovery"])
async def diff_snapshots(
    snapshot_a_id: str = Query(..., description="First snapshot ID"),
    snapshot_b_id: str = Query(..., description="Second snapshot ID"),
):
    """Compare two snapshots."""
    recovery = get_recovery()
    return await recovery.diff(snapshot_a_id, snapshot_b_id)


@app.post("/api/v1/diff", response_model=DiffResult, tags=["Recovery"])
async def diff_snapshots_post(request: DiffRequest):
    """Compare two snapshots (POST variant)."""
    recovery = get_recovery()
    return await recovery.diff(request.snapshot_a_id, request.snapshot_b_id)


# Rollback endpoints

@app.post("/api/v1/rollback", response_model=RollbackResult, tags=["Recovery"])
async def execute_rollback(request: RollbackRequest):
    """Execute a rollback to a specific snapshot."""
    recovery = get_recovery()
    return await recovery.rollback(request)


@app.get("/api/v1/rollback/preview", tags=["Recovery"])
async def preview_rollback(
    session_id: str = Query(..., description="Session ID"),
    target_snapshot_id: str = Query(..., description="Target snapshot ID"),
):
    """Preview what a rollback would do."""
    recovery = get_recovery()
    return await recovery.get_rollback_preview(session_id, target_snapshot_id)


# Replay endpoints

@app.post("/api/v1/replay", response_model=ReplayResult, tags=["Recovery"])
async def execute_replay(request: ReplayRequest):
    """Replay actions from a snapshot."""
    recovery = get_recovery()
    return await recovery.replay(request)


# Recovery points endpoint

@app.get("/api/v1/sessions/{session_id}/recovery-points", tags=["Recovery"])
async def list_recovery_points(
    session_id: str = Path(..., description="Session ID"),
    include_checkpoints: bool = Query(default=True, description="Include checkpoints"),
    include_before_snapshots: bool = Query(default=True, description="Include before-action snapshots"),
):
    """List all possible recovery points for a session."""
    recovery = get_recovery()
    return await recovery.list_recovery_points(
        session_id,
        include_checkpoints=include_checkpoints,
        include_before_snapshots=include_before_snapshots,
    )


def create_app(db_path: str = "agent_rollback.db") -> FastAPI:
    """Create a new FastAPI app with custom configuration.

    Args:
        db_path: Path to SQLite database

    Returns:
        Configured FastAPI app
    """
    global _store, _tracker, _recovery

    _store = StateStore(db_path=db_path)
    _tracker = StateTracker(store=_store)
    _recovery = RecoveryEngine(store=_store)

    return app


def run_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    db_path: str = "agent_rollback.db",
    reload: bool = False,
):
    """Run the API server.

    Args:
        host: Host to bind to
        port: Port to bind to
        db_path: Path to SQLite database
        reload: Enable auto-reload for development
    """
    import uvicorn

    # Set up the store before running
    global _store, _tracker, _recovery
    _store = StateStore(db_path=db_path)
    _tracker = StateTracker(store=_store)
    _recovery = RecoveryEngine(store=_store)

    uvicorn.run(
        "agent_rollback.server:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    run_server()
