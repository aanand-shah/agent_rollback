-- AgentRollback Database Schema
-- SQLite initialization script

-- Sessions table: tracks agent tracking sessions
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    metadata JSON,
    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'completed', 'failed', 'rolled_back'))
);

-- Snapshots table: stores state snapshots
CREATE TABLE IF NOT EXISTS snapshots (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    action_id TEXT,
    connector_type TEXT NOT NULL,
    connector_id TEXT,
    state_data JSON NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    snapshot_type TEXT NOT NULL CHECK(snapshot_type IN ('before', 'after', 'checkpoint'))
);

-- Actions table: records individual agent actions
CREATE TABLE IF NOT EXISTS actions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL,
    action_data JSON,
    before_snapshot_id TEXT REFERENCES snapshots(id),
    after_snapshot_id TEXT REFERENCES snapshots(id),
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'completed' CHECK(status IN ('pending', 'completed', 'failed', 'rolled_back')),
    parent_action_id TEXT REFERENCES actions(id)
);

-- Connectors table: registered external system connectors
CREATE TABLE IF NOT EXISTS connectors (
    connector_type TEXT NOT NULL,
    connector_id TEXT NOT NULL,
    config JSON,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (connector_type, connector_id)
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_sessions_agent ON sessions(agent_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_snapshots_session ON snapshots(session_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_action ON snapshots(action_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_type ON snapshots(snapshot_type);
CREATE INDEX IF NOT EXISTS idx_snapshots_connector ON snapshots(connector_type, connector_id);
CREATE INDEX IF NOT EXISTS idx_actions_session ON actions(session_id);
CREATE INDEX IF NOT EXISTS idx_actions_time ON actions(executed_at);
CREATE INDEX IF NOT EXISTS idx_actions_status ON actions(status);
CREATE INDEX IF NOT EXISTS idx_actions_parent ON actions(parent_action_id);
