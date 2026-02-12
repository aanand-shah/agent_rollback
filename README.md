# AgentRollback

**Git for AI Agents** - A middleware layer that captures state snapshots before/after each agent action, enabling point-in-time recovery.


## Overview

Enterprise AI agents interact with multiple external systems (databases, APIs, file systems) and their state changes can have cascading effects. AgentRollback provides:

- **State Tracking**: Capture before/after snapshots for every agent action
- **Point-in-Time Recovery**: Rollback to any previous state
- **Action Replay**: Re-execute actions from a specific point
- **State Diffing**: Compare snapshots to understand what changed
- **Multi-System Support**: Connectors for databases, files, APIs, and memory

## Installation

```bash
# Clone or download the package
cd agent_rollback

# Install dependencies
pip install -r requirements.txt

# Install the package
pip install -e .
```

### Dependencies

- Python 3.10+
- FastAPI, Uvicorn (REST API)
- Pydantic (Data models)
- aiosqlite (Async SQLite)
- Click, Rich (CLI)
- httpx (HTTP client)

## Quick Start

### Option 1: Web Dashboard (Recommended)

The easiest way to get started is with the web dashboard:

```bash
# Install dependencies
pip install -r requirements.txt

# Start the dashboard
python run_dashboard.py

# Open http://localhost:8000 in your browser
```

The dashboard provides:
- Real-time session monitoring
- Visual timeline of agent actions
- One-click rollback to any checkpoint
- Built-in demo AI Sales Agent

### Option 2: Run the Demo Agent

Try the AI Sales Agent demo to see rollback in action:

```bash
# Automated demo (runs through a complete scenario)
python run_demo.py

# Interactive demo (manual control)
python run_demo.py --interactive
```

The demo simulates a CRM workflow where an AI agent:
1. Imports and qualifies leads
2. Creates opportunities
3. Closes deals
4. Encounters an error (data corruption)
5. Rolls back to recover

### Option 3: Python SDK (Local Mode)

```python
import asyncio
from agent_rollback import AgentRollbackClient

async def main():
    # Create client in local mode (no server needed)
    client = AgentRollbackClient(local=True)

    async with client:
        # Start tracking session
        session = await client.start_session(agent_id="my-agent")

        # Record actions with state
        await client.record_action(
            action_type="update_database",
            action_data={"table": "users", "operation": "insert"},
            before_state={"user_count": 10},
            after_state={"user_count": 11},
        )

        # Create checkpoint
        checkpoint = await client.create_checkpoint(
            state_data={"user_count": 11}
        )

        # More actions...
        await client.record_action(
            action_type="delete_user",
            before_state={"user_count": 11},
            after_state={"user_count": 10},
        )

        # Rollback to checkpoint
        result = await client.rollback(checkpoint.id)
        print(f"Rolled back {result.actions_reverted} actions")

asyncio.run(main())
```

### Option 2: REST API

```bash
# Start the server
python -m agent_rollback serve

# Server runs at http://localhost:8000
# API docs at http://localhost:8000/docs
```

```python
import httpx

# Create session
response = httpx.post("http://localhost:8000/api/v1/sessions", json={
    "agent_id": "my-agent"
})
session_id = response.json()["session"]["id"]

# Record action
httpx.post(f"http://localhost:8000/api/v1/sessions/{session_id}/actions", json={
    "session_id": session_id,
    "action_type": "api_call",
    "action_data": {"endpoint": "/users"},
    "before_state": {"calls": 0},
    "after_state": {"calls": 1},
})

# Create checkpoint
response = httpx.post(f"http://localhost:8000/api/v1/sessions/{session_id}/checkpoint", json={
    "state_data": {"calls": 1}
})
checkpoint_id = response.json()["snapshot"]["id"]

# Rollback
httpx.post("http://localhost:8000/api/v1/rollback", json={
    "session_id": session_id,
    "target_snapshot_id": checkpoint_id
})
```

### Option 3: CLI

```bash
# View system status
agentrollback status

# List sessions
agentrollback sessions
agentrollback sessions --status active

# View session history
agentrollback log <session_id>
agentrollback log abc123 --limit 50

# List snapshots
agentrollback snapshots <session_id>

# Compare snapshots
agentrollback diff <snapshot_a> <snapshot_b>

# Rollback (with preview)
agentrollback rollback <session_id> <snapshot_id> --dry-run
agentrollback rollback <session_id> <snapshot_id>

# Export session data
agentrollback export <session_id> -o session_backup.json

# Start API server
agentrollback serve --host 0.0.0.0 --port 8000
```

## Core Concepts

### Sessions

A session represents a tracking period for an agent. All actions and snapshots belong to a session.

```python
session = await client.start_session(
    agent_id="data-processing-agent",
    metadata={"task": "ETL pipeline", "version": "2.0"}
)

# ... do work ...

await client.end_session(status=SessionStatus.COMPLETED)
```

### Actions

Actions represent individual operations performed by the agent. Each action can have before/after state snapshots.

```python
action = await client.record_action(
    action_type="database_insert",
    action_data={
        "table": "orders",
        "record_id": 12345,
        "data": {"amount": 99.99}
    },
    before_state={"order_count": 100},
    after_state={"order_count": 101},
    connector_type="database",
)
```

### Snapshots

Snapshots capture system state at a point in time. Types:
- **before**: State before an action
- **after**: State after an action
- **checkpoint**: Manual save point

```python
# Automatic snapshots (via actions)
await client.record_action(
    action_type="update",
    before_state=old_state,  # Creates 'before' snapshot
    after_state=new_state,   # Creates 'after' snapshot
)

# Manual checkpoint
checkpoint = await client.create_checkpoint(
    state_data=current_state,
    connector_type="memory",
)
```

### Connectors

Connectors interface with external systems to capture and restore state.

```python
from agent_rollback.connectors import (
    FileSystemConnector,
    MemoryConnector,
    DatabaseConnector,
    APIConnector,
)

# File system connector
fs_connector = FileSystemConnector(
    connector_id="project-files",
    config={
        "base_path": "/app/data",
        "patterns": ["**/*.json", "**/*.csv"],
        "exclude_patterns": ["**/temp/*"],
    }
)

# Capture file state
state = await fs_connector.capture_state()

# Restore file state
await fs_connector.restore_state(state)
```

## SDK Reference

### AgentRollbackClient

```python
from agent_rollback import AgentRollbackClient

# Local mode (direct database access)
client = AgentRollbackClient(
    local=True,
    db_path="agent_rollback.db"
)

# API mode (connects to server)
client = AgentRollbackClient(
    base_url="http://localhost:8000",
    api_key="optional-api-key",
    timeout=30.0
)

# Context manager usage
async with client:
    session = await client.start_session("agent-id")
    # ... work ...
    await client.end_session()

# Session context manager
async with client.session("agent-id", auto_checkpoint=True) as session:
    await client.record_action(...)
    # Auto-checkpoints and ends session on exit
```

### @track_action Decorator

```python
from agent_rollback import track_action, AgentRollbackClient

client = AgentRollbackClient(local=True)

@track_action("process_data", client=client)
async def process_data(input_file: str):
    # Function execution is automatically tracked
    result = do_processing(input_file)
    return result

# With state capture
def get_current_state():
    return {"processed_files": len(processed_list)}

@track_action("process_data", client=client, capture_state=get_current_state)
async def process_data(input_file: str):
    # Before/after state captured automatically
    ...
```

### TrackedAgent Base Class

```python
from agent_rollback.sdk import TrackedAgent

class MyAgent(TrackedAgent):
    async def do_task(self, task_data):
        # Record action
        await self.record_action(
            action_type="task_execution",
            action_data=task_data,
        )

        # Create checkpoint
        await self.checkpoint(state_data={"task": "completed"})

# Usage
async with MyAgent("my-agent", local=True) as agent:
    await agent.do_task({"name": "process"})
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/sessions` | Create new session |
| GET | `/api/v1/sessions` | List sessions |
| GET | `/api/v1/sessions/{id}` | Get session details |
| DELETE | `/api/v1/sessions/{id}` | End session |
| GET | `/api/v1/sessions/{id}/timeline` | Get session timeline |
| POST | `/api/v1/sessions/{id}/actions` | Record action |
| GET | `/api/v1/sessions/{id}/actions` | List actions |
| POST | `/api/v1/sessions/{id}/checkpoint` | Create checkpoint |
| GET | `/api/v1/sessions/{id}/snapshots` | List snapshots |
| GET | `/api/v1/snapshots/{id}` | Get snapshot details |
| GET | `/api/v1/diff` | Compare two snapshots |
| POST | `/api/v1/rollback` | Execute rollback |
| GET | `/api/v1/rollback/preview` | Preview rollback |
| POST | `/api/v1/replay` | Replay actions |
| GET | `/api/v1/sessions/{id}/recovery-points` | List recovery points |

## CLI Commands

```
agentrollback [OPTIONS] COMMAND [ARGS]

Options:
  --db PATH  Database path (default: agent_rollback.db)

Commands:
  status     Show active sessions and system status
  sessions   List tracking sessions
  log        Show action history for a session
  snapshots  List snapshots for a session
  diff       Show differences between two snapshots
  rollback   Rollback a session to a specific snapshot
  export     Export session data to JSON/YAML
  serve      Start the REST API server
```

### Examples

```bash
# Status overview
agentrollback status

# List active sessions
agentrollback sessions

# List all sessions
agentrollback sessions --all

# Filter by status
agentrollback sessions --status completed

# View session log
agentrollback log abc12345

# View with JSON output
agentrollback log abc12345 --json-output

# List snapshots
agentrollback snapshots abc12345

# Diff two snapshots
agentrollback diff snap1 snap2 --color

# Preview rollback
agentrollback rollback abc12345 snap1 --dry-run

# Execute rollback
agentrollback rollback abc12345 snap1 --force

# Export session
agentrollback export abc12345 -o backup.json

# Start server
agentrollback serve --host 0.0.0.0 --port 8000 --reload
```

## Examples

### Basic Usage

```python
# examples/basic_usage.py
import asyncio
from agent_rollback import AgentRollbackClient, SessionStatus

async def main():
    client = AgentRollbackClient(local=True, db_path="example.db")

    async with client:
        session = await client.start_session("example-agent")

        # Track state changes
        await client.record_action(
            action_type="initialize",
            after_state={"counter": 0, "items": []}
        )

        await client.record_action(
            action_type="add_item",
            before_state={"counter": 0, "items": []},
            after_state={"counter": 1, "items": ["item1"]}
        )

        # Checkpoint
        checkpoint = await client.create_checkpoint(
            state_data={"counter": 1, "items": ["item1"]}
        )

        # More changes...
        await client.record_action(
            action_type="error_operation",
            before_state={"counter": 1},
            after_state={"counter": -1, "error": True}
        )

        # Rollback to checkpoint
        result = await client.rollback(checkpoint.id, dry_run=True)
        print(f"Would revert {result.actions_reverted} actions")

asyncio.run(main())
```

### LangChain Integration

```python
# examples/langchain_integration.py
from agent_rollback.sdk import TrackedAgent

class LangChainAgent(TrackedAgent):
    def wrap_tool(self, tool):
        """Wrap a LangChain tool with tracking."""
        original_run = tool.run

        async def tracked_run(*args, **kwargs):
            before_state = self.capture_state()
            result = original_run(*args, **kwargs)
            after_state = self.capture_state()

            await self.record_action(
                action_type=f"tool:{tool.name}",
                action_data={"args": args, "result": result},
                before_state=before_state,
                after_state=after_state,
            )
            return result

        tool.run = tracked_run
        return tool
```

### Webhook Integration

```python
# examples/webhook_integration.py
import httpx

BASE_URL = "http://localhost:8000"

async def agent_workflow():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # Start session
        resp = await client.post("/api/v1/sessions", json={
            "agent_id": "webhook-agent"
        })
        session_id = resp.json()["session"]["id"]

        # Record actions via webhooks
        await client.post(f"/api/v1/sessions/{session_id}/actions", json={
            "session_id": session_id,
            "action_type": "api_call",
            "action_data": {"endpoint": "/users"},
            "before_state": {"calls": 0},
            "after_state": {"calls": 1},
        })

        # Create checkpoint
        resp = await client.post(
            f"/api/v1/sessions/{session_id}/checkpoint",
            json={"state_data": {"calls": 1}}
        )
        checkpoint_id = resp.json()["snapshot"]["id"]

        # Rollback if needed
        await client.post("/api/v1/rollback", json={
            "session_id": session_id,
            "target_snapshot_id": checkpoint_id,
            "dry_run": False
        })
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      AI Agent Application                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AgentRollback Middleware                      │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │   Tracker   │  │  State Store │  │   Recovery Engine      │  │
│  │  (Webhooks) │  │   (SQLite)   │  │ (Rollback/Replay/Diff) │  │
│  └─────────────┘  └──────────────┘  └────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│               Connected Systems (via Connectors)                 │
│    [Database]    [File System]    [APIs]    [Memory/Redis]      │
└─────────────────────────────────────────────────────────────────┘
```

## Database Schema

```sql
-- Sessions: Agent tracking sessions
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    metadata JSON,
    status TEXT  -- active, completed, failed, rolled_back
);

-- Snapshots: State captures
CREATE TABLE snapshots (
    id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES sessions(id),
    action_id TEXT,
    connector_type TEXT NOT NULL,
    connector_id TEXT,
    state_data JSON NOT NULL,
    created_at TIMESTAMP,
    snapshot_type TEXT  -- before, after, checkpoint
);

-- Actions: Agent operations
CREATE TABLE actions (
    id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES sessions(id),
    action_type TEXT NOT NULL,
    action_data JSON,
    before_snapshot_id TEXT REFERENCES snapshots(id),
    after_snapshot_id TEXT REFERENCES snapshots(id),
    executed_at TIMESTAMP,
    status TEXT,
    parent_action_id TEXT  -- For nested operations
);
```

## Web Dashboard

The web dashboard provides a visual interface for managing agent state:

### Features

- **Dashboard Overview**: See all sessions at a glance with status indicators
- **Session Timeline**: Visual timeline of all actions in a session
- **Checkpoint Management**: Create and manage recovery points
- **One-Click Rollback**: Preview and execute rollbacks with a single click
- **State Diff Viewer**: Compare any two snapshots to see what changed
- **Built-in Demo**: Interactive AI Sales Agent demo to test the system

### Running the Dashboard

```bash
# Basic usage
python run_dashboard.py

# Custom host/port
python run_dashboard.py --host 0.0.0.0 --port 8080

# Development mode with auto-reload
python run_dashboard.py --reload
```

### Dashboard URLs

- **Main Dashboard**: http://localhost:8000/
- **API Documentation**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

## Demo AI Sales Agent

The demo simulates a real-world AI sales agent scenario:

### Scenario

1. **Lead Import**: AI imports leads from external source
2. **Lead Qualification**: AI scores and qualifies leads
3. **Opportunity Creation**: Qualified leads become opportunities
4. **Pipeline Management**: AI advances opportunities through stages
5. **Deal Closing**: AI closes deals and tracks revenue
6. **Error Simulation**: Intentional data corruption
7. **Recovery**: Rollback to restore good state

### Running the Demo

```bash
# Automated demo (runs complete scenario)
python run_demo.py

# Interactive mode (manual control)
python run_demo.py --interactive
```

### Interactive Commands

```
import      - Import sample leads
qualify     - Qualify all new leads
convert     - Convert qualified leads to opportunities
advance     - Advance opportunities to next stage
close       - Close deals
checkpoint  - Create a checkpoint
error       - Simulate an error (corrupts data)
rollback    - Rollback to last checkpoint
status      - Show CRM status
snapshots   - List available snapshots
quit        - Exit demo
```

## Project Structure

```
agent_rollback/
├── __init__.py          # Package exports
├── models.py            # Pydantic data models
├── store.py             # SQLite storage layer
├── tracker.py           # State tracking
├── recovery.py          # Rollback/replay engine
├── server.py            # FastAPI REST API
├── sdk.py               # Python SDK
├── cli.py               # CLI tool
├── connectors/          # System connectors
└── utils/               # Utilities

frontend/
├── app.py               # Dashboard server
├── templates/           # HTML templates
└── static/              # CSS & JavaScript

demo/
├── sales_agent.py       # AI Sales Agent demo
└── __init__.py

examples/
├── basic_usage.py
├── langchain_integration.py
└── webhook_integration.py
```

## License

MIT License
