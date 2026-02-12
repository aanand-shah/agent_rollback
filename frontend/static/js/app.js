/**
 * AgentRollback Dashboard Application
 */

const API_BASE = window.location.origin;

// State
const state = {
    sessions: [],
    currentSession: null,
    actions: [],
    snapshots: [],
    demoAgent: null,
    crmData: {
        leads: [],
        opportunities: [],
        customers: []
    }
};

// API Functions
const api = {
    async get(endpoint) {
        const response = await fetch(`${API_BASE}${endpoint}`);
        if (!response.ok) throw new Error(`API Error: ${response.status}`);
        return response.json();
    },

    async post(endpoint, data) {
        const response = await fetch(`${API_BASE}${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(`API Error: ${response.status}`);
        return response.json();
    },

    async delete(endpoint) {
        const response = await fetch(`${API_BASE}${endpoint}`, {
            method: 'DELETE'
        });
        if (!response.ok) throw new Error(`API Error: ${response.status}`);
        return response.json();
    }
};

// Dashboard Functions
async function loadDashboard() {
    try {
        showLoading('stats-container');
        const sessions = await api.get('/api/v1/sessions?limit=100');
        state.sessions = sessions.sessions || [];
        renderStats();
        renderSessionsTable();
    } catch (error) {
        showError('Failed to load dashboard: ' + error.message);
    }
}

function renderStats() {
    const active = state.sessions.filter(s => s.status === 'active').length;
    const completed = state.sessions.filter(s => s.status === 'completed').length;
    const failed = state.sessions.filter(s => s.status === 'failed').length;
    const rolledBack = state.sessions.filter(s => s.status === 'rolled_back').length;

    document.getElementById('stat-active').textContent = active;
    document.getElementById('stat-completed').textContent = completed;
    document.getElementById('stat-failed').textContent = failed;
    document.getElementById('stat-rollbacks').textContent = rolledBack;
}

function renderSessionsTable() {
    const tbody = document.getElementById('sessions-tbody');
    if (!tbody) return;

    if (state.sessions.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="empty-state">
                    <div class="empty-state-icon">📭</div>
                    <p>No sessions found. Start the demo agent to create some!</p>
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = state.sessions.map(session => `
        <tr onclick="viewSession('${session.id}')" style="cursor: pointer;">
            <td><code class="mono">${session.id.substring(0, 8)}...</code></td>
            <td>${session.agent_id}</td>
            <td>${getStatusBadge(session.status)}</td>
            <td>${formatDate(session.started_at)}</td>
            <td>${session.ended_at ? formatDuration(session.started_at, session.ended_at) : 'Ongoing'}</td>
            <td>
                <div class="action-buttons">
                    <button class="btn btn-sm btn-secondary" onclick="event.stopPropagation(); viewSession('${session.id}')">
                        <i class="fas fa-eye"></i>
                    </button>
                    ${session.status === 'active' ? `
                        <button class="btn btn-sm btn-danger" onclick="event.stopPropagation(); endSession('${session.id}')">
                            <i class="fas fa-stop"></i>
                        </button>
                    ` : ''}
                </div>
            </td>
        </tr>
    `).join('');
}

async function viewSession(sessionId) {
    try {
        state.currentSession = sessionId;

        // Fetch session details, actions, and snapshots
        const [sessionData, actionsData, snapshotsData] = await Promise.all([
            api.get(`/api/v1/sessions/${sessionId}`),
            api.get(`/api/v1/sessions/${sessionId}/actions?limit=100`),
            api.get(`/api/v1/sessions/${sessionId}/snapshots?limit=100`)
        ]);

        state.actions = actionsData.actions || [];
        state.snapshots = snapshotsData.snapshots || [];

        showSessionModal(sessionData.session);
    } catch (error) {
        showError('Failed to load session: ' + error.message);
    }
}

function showSessionModal(session) {
    const modal = document.getElementById('session-modal');

    document.getElementById('modal-session-id').textContent = session.id;
    document.getElementById('modal-agent-id').textContent = session.agent_id;
    document.getElementById('modal-session-status').innerHTML = getStatusBadge(session.status);
    document.getElementById('modal-started-at').textContent = formatDate(session.started_at);
    document.getElementById('modal-ended-at').textContent = session.ended_at ? formatDate(session.ended_at) : 'Active';

    // Render timeline
    renderTimeline();

    // Render snapshots list
    renderSnapshotsList();

    modal.classList.add('active');
}

function renderTimeline() {
    const container = document.getElementById('timeline-container');

    if (state.actions.length === 0) {
        container.innerHTML = '<div class="empty-state">No actions recorded</div>';
        return;
    }

    container.innerHTML = `
        <div class="timeline">
            ${state.actions.map(action => `
                <div class="timeline-item">
                    <div class="timeline-marker ${getActionMarkerClass(action.status)}"></div>
                    <div class="timeline-content">
                        <div class="timeline-time">${formatTime(action.executed_at)}</div>
                        <div class="timeline-title">${action.action_type}</div>
                        ${action.action_data ? `
                            <div class="timeline-description">
                                ${truncateJson(action.action_data)}
                            </div>
                        ` : ''}
                        ${action.before_snapshot_id ? `
                            <button class="btn btn-sm btn-secondary" style="margin-top: 0.5rem;"
                                onclick="showSnapshot('${action.before_snapshot_id}')">
                                View Before State
                            </button>
                        ` : ''}
                        ${action.after_snapshot_id ? `
                            <button class="btn btn-sm btn-secondary" style="margin-top: 0.5rem;"
                                onclick="showSnapshot('${action.after_snapshot_id}')">
                                View After State
                            </button>
                        ` : ''}
                    </div>
                </div>
            `).join('')}
        </div>
    `;
}

function renderSnapshotsList() {
    const container = document.getElementById('snapshots-list');

    const checkpoints = state.snapshots.filter(s => s.snapshot_type === 'checkpoint');

    if (checkpoints.length === 0) {
        container.innerHTML = '<div class="empty-state">No checkpoints available</div>';
        return;
    }

    container.innerHTML = checkpoints.map(snapshot => `
        <div class="card" style="margin-bottom: 0.75rem; padding: 1rem;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <div class="mono" style="font-size: 0.8125rem;">${snapshot.id.substring(0, 12)}...</div>
                    <div style="color: var(--gray-500); font-size: 0.8125rem;">${formatTime(snapshot.created_at)}</div>
                </div>
                <div class="action-buttons">
                    <button class="btn btn-sm btn-secondary" onclick="showSnapshot('${snapshot.id}')">
                        <i class="fas fa-eye"></i> View
                    </button>
                    <button class="btn btn-sm btn-warning" onclick="confirmRollback('${snapshot.id}')">
                        <i class="fas fa-undo"></i> Rollback
                    </button>
                </div>
            </div>
        </div>
    `).join('');
}

async function showSnapshot(snapshotId) {
    try {
        const data = await api.get(`/api/v1/snapshots/${snapshotId}`);
        const snapshot = data.snapshot;

        const content = `
            <div class="form-group">
                <label class="form-label">Snapshot ID</label>
                <code class="mono">${snapshot.id}</code>
            </div>
            <div class="form-group">
                <label class="form-label">Type</label>
                ${getSnapshotTypeBadge(snapshot.snapshot_type)}
            </div>
            <div class="form-group">
                <label class="form-label">Connector</label>
                <code>${snapshot.connector_type}${snapshot.connector_id ? ':' + snapshot.connector_id : ''}</code>
            </div>
            <div class="form-group">
                <label class="form-label">Created At</label>
                <span>${formatDate(snapshot.created_at)}</span>
            </div>
            <div class="form-group">
                <label class="form-label">State Data</label>
                <pre class="json-view">${JSON.stringify(snapshot.state_data, null, 2)}</pre>
            </div>
        `;

        showGenericModal('Snapshot Details', content);
    } catch (error) {
        showError('Failed to load snapshot: ' + error.message);
    }
}

async function confirmRollback(snapshotId) {
    if (!state.currentSession) return;

    try {
        // Get preview first
        const preview = await api.get(`/api/v1/rollback/preview?session_id=${state.currentSession}&target_snapshot_id=${snapshotId}`);

        const content = `
            <div class="alert alert-warning">
                <i class="fas fa-exclamation-triangle"></i>
                <span>This will revert <strong>${preview.actions_to_revert}</strong> action(s)</span>
            </div>
            <div class="form-group">
                <label class="form-label">Actions to Revert</label>
                <p>${preview.action_types.join(', ') || 'None'}</p>
            </div>
            <div class="form-group">
                <label class="form-label">Target Time</label>
                <p>${formatDate(preview.target_snapshot_time)}</p>
            </div>
        `;

        showConfirmModal('Confirm Rollback', content, async () => {
            await executeRollback(snapshotId);
        });
    } catch (error) {
        showError('Failed to preview rollback: ' + error.message);
    }
}

async function executeRollback(snapshotId) {
    try {
        const result = await api.post('/api/v1/rollback', {
            session_id: state.currentSession,
            target_snapshot_id: snapshotId,
            dry_run: false
        });

        if (result.success) {
            showSuccess(`Rollback successful! Reverted ${result.actions_reverted} actions.`);
            closeModal('confirm-modal');
            closeModal('session-modal');
            loadDashboard();
        } else {
            showError('Rollback failed: ' + result.errors.join(', '));
        }
    } catch (error) {
        showError('Rollback failed: ' + error.message);
    }
}

async function endSession(sessionId) {
    try {
        await api.delete(`/api/v1/sessions/${sessionId}?status=completed`);
        showSuccess('Session ended successfully');
        loadDashboard();
    } catch (error) {
        showError('Failed to end session: ' + error.message);
    }
}

// Diff Functions
async function showDiff(snapshotAId, snapshotBId) {
    try {
        const result = await api.get(`/api/v1/diff?snapshot_a_id=${snapshotAId}&snapshot_b_id=${snapshotBId}`);

        const diffHtml = result.changes.length > 0
            ? result.changes.map(change => `
                <div class="diff-line ${change.operation}">
                    ${change.operation === 'add' ? '+' : change.operation === 'remove' ? '-' : '~'}
                    ${change.path}: ${change.operation === 'modify'
                        ? `${JSON.stringify(change.old_value)} → ${JSON.stringify(change.new_value)}`
                        : JSON.stringify(change.new_value || change.old_value)}
                </div>
            `).join('')
            : '<div class="diff-line">No changes detected</div>';

        const content = `
            <div class="form-group">
                <label class="form-label">Summary</label>
                <p>${result.summary}</p>
            </div>
            <div class="form-group">
                <label class="form-label">Changes</label>
                <div class="diff-view">${diffHtml}</div>
            </div>
        `;

        showGenericModal('State Diff', content);
    } catch (error) {
        showError('Failed to compute diff: ' + error.message);
    }
}

// Demo Agent Functions
class DemoSalesAgent {
    constructor() {
        this.sessionId = null;
        this.running = false;
        this.actionCount = 0;
    }

    async start() {
        try {
            const response = await api.post('/api/v1/sessions', {
                agent_id: 'sales-ai-agent',
                metadata: {
                    type: 'demo',
                    description: 'AI Sales Agent Demo'
                }
            });
            this.sessionId = response.session.id;
            this.running = true;
            this.actionCount = 0;
            addLogEntry('Agent started - Session: ' + this.sessionId.substring(0, 8), 'success');
            updateDemoStatus('running');
            return this.sessionId;
        } catch (error) {
            addLogEntry('Failed to start agent: ' + error.message, 'error');
            throw error;
        }
    }

    async stop() {
        if (!this.sessionId) return;
        try {
            await api.delete(`/api/v1/sessions/${this.sessionId}?status=completed`);
            addLogEntry('Agent stopped', 'info');
            this.running = false;
            updateDemoStatus('stopped');
            loadDashboard();
        } catch (error) {
            addLogEntry('Failed to stop agent: ' + error.message, 'error');
        }
    }

    async recordAction(actionType, actionData, beforeState, afterState) {
        if (!this.sessionId || !this.running) return;
        try {
            await api.post(`/api/v1/sessions/${this.sessionId}/actions`, {
                session_id: this.sessionId,
                action_type: actionType,
                action_data: actionData,
                before_state: beforeState,
                after_state: afterState,
                connector_type: 'crm'
            });
            this.actionCount++;
            addLogEntry(`Action: ${actionType}`, 'info');
        } catch (error) {
            addLogEntry(`Failed to record action: ${error.message}`, 'error');
        }
    }

    async createCheckpoint(stateData) {
        if (!this.sessionId) return;
        try {
            const response = await api.post(`/api/v1/sessions/${this.sessionId}/checkpoint`, {
                connector_type: 'crm',
                state_data: stateData
            });
            addLogEntry('Checkpoint created: ' + response.snapshot.id.substring(0, 8), 'success');
            return response.snapshot;
        } catch (error) {
            addLogEntry('Failed to create checkpoint: ' + error.message, 'error');
        }
    }
}

// CRM Simulation
const crmSimulation = {
    leads: [
        { id: 'L001', name: 'Acme Corp', email: 'contact@acme.com', value: 50000, status: 'new' },
        { id: 'L002', name: 'TechStart Inc', email: 'sales@techstart.io', value: 25000, status: 'new' },
        { id: 'L003', name: 'Global Systems', email: 'info@globalsys.com', value: 100000, status: 'new' }
    ],
    opportunities: [],
    customers: [],
    revenue: 0
};

function renderCRM() {
    const container = document.getElementById('crm-container');
    if (!container) return;

    const allItems = [
        ...crmSimulation.leads.map(l => ({ ...l, type: 'lead' })),
        ...crmSimulation.opportunities.map(o => ({ ...o, type: 'opportunity' })),
        ...crmSimulation.customers.map(c => ({ ...c, type: 'customer' }))
    ];

    if (allItems.length === 0) {
        container.innerHTML = '<div class="empty-state">No CRM data</div>';
        return;
    }

    container.innerHTML = `
        <div class="crm-grid">
            ${allItems.map(item => `
                <div class="crm-card ${item.type}">
                    <div class="crm-card-header">
                        <div class="crm-card-title">${item.name}</div>
                        ${getStatusBadge(item.status || item.type)}
                    </div>
                    <div class="crm-card-meta">${item.email}</div>
                    <div class="crm-card-value">$${item.value.toLocaleString()}</div>
                </div>
            `).join('')}
        </div>
    `;

    // Update stats
    document.getElementById('crm-leads').textContent = crmSimulation.leads.length;
    document.getElementById('crm-opportunities').textContent = crmSimulation.opportunities.length;
    document.getElementById('crm-customers').textContent = crmSimulation.customers.length;
    document.getElementById('crm-revenue').textContent = '$' + crmSimulation.revenue.toLocaleString();
}

async function runDemoScenario(scenario) {
    if (!state.demoAgent || !state.demoAgent.running) {
        showError('Please start the agent first');
        return;
    }

    const beforeState = JSON.parse(JSON.stringify(crmSimulation));

    switch (scenario) {
        case 'qualify-lead':
            await qualifyLead();
            break;
        case 'convert-opportunity':
            await convertOpportunity();
            break;
        case 'close-deal':
            await closeDeal();
            break;
        case 'simulate-error':
            await simulateError();
            break;
    }

    const afterState = JSON.parse(JSON.stringify(crmSimulation));
    await state.demoAgent.recordAction(scenario, { scenario }, beforeState, afterState);
    renderCRM();
}

async function qualifyLead() {
    if (crmSimulation.leads.length === 0) {
        addLogEntry('No leads to qualify', 'warning');
        return;
    }

    const lead = crmSimulation.leads.shift();
    lead.status = 'qualified';
    crmSimulation.opportunities.push(lead);
    addLogEntry(`Qualified lead: ${lead.name}`, 'success');
}

async function convertOpportunity() {
    if (crmSimulation.opportunities.length === 0) {
        addLogEntry('No opportunities to convert', 'warning');
        return;
    }

    const opp = crmSimulation.opportunities.shift();
    opp.status = 'customer';
    crmSimulation.customers.push(opp);
    addLogEntry(`Converted opportunity: ${opp.name}`, 'success');
}

async function closeDeal() {
    if (crmSimulation.customers.length === 0) {
        addLogEntry('No customers with pending deals', 'warning');
        return;
    }

    const customer = crmSimulation.customers[crmSimulation.customers.length - 1];
    crmSimulation.revenue += customer.value;
    addLogEntry(`Closed deal: $${customer.value.toLocaleString()} from ${customer.name}`, 'success');
}

async function simulateError() {
    // Simulate a bad action - corrupt data
    addLogEntry('Simulating error: Corrupting CRM data...', 'error');
    crmSimulation.leads = [];
    crmSimulation.opportunities = [];
    crmSimulation.customers = [];
    crmSimulation.revenue = -99999;
    addLogEntry('CRM data corrupted! Use rollback to recover.', 'error');
}

async function createDemoCheckpoint() {
    if (!state.demoAgent || !state.demoAgent.running) {
        showError('Please start the agent first');
        return;
    }

    await state.demoAgent.createCheckpoint(JSON.parse(JSON.stringify(crmSimulation)));
}

async function resetCRM() {
    crmSimulation.leads = [
        { id: 'L001', name: 'Acme Corp', email: 'contact@acme.com', value: 50000, status: 'new' },
        { id: 'L002', name: 'TechStart Inc', email: 'sales@techstart.io', value: 25000, status: 'new' },
        { id: 'L003', name: 'Global Systems', email: 'info@globalsys.com', value: 100000, status: 'new' }
    ];
    crmSimulation.opportunities = [];
    crmSimulation.customers = [];
    crmSimulation.revenue = 0;
    renderCRM();
    addLogEntry('CRM reset to initial state', 'info');
}

// UI Helpers
function showLoading(containerId) {
    const container = document.getElementById(containerId);
    if (container) {
        container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
    }
}

function showError(message) {
    const alertContainer = document.getElementById('alert-container');
    if (alertContainer) {
        alertContainer.innerHTML = `
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-circle"></i>
                <span>${message}</span>
            </div>
        `;
        setTimeout(() => alertContainer.innerHTML = '', 5000);
    }
    console.error(message);
}

function showSuccess(message) {
    const alertContainer = document.getElementById('alert-container');
    if (alertContainer) {
        alertContainer.innerHTML = `
            <div class="alert alert-success">
                <i class="fas fa-check-circle"></i>
                <span>${message}</span>
            </div>
        `;
        setTimeout(() => alertContainer.innerHTML = '', 5000);
    }
}

function showGenericModal(title, content) {
    const existingModal = document.getElementById('generic-modal');
    if (existingModal) existingModal.remove();

    const modal = document.createElement('div');
    modal.id = 'generic-modal';
    modal.className = 'modal-backdrop';
    modal.innerHTML = `
        <div class="modal">
            <div class="modal-header">
                <h3 class="modal-title">${title}</h3>
                <button class="modal-close" onclick="closeModal('generic-modal')">&times;</button>
            </div>
            <div class="modal-body">${content}</div>
            <div class="modal-footer">
                <button class="btn btn-secondary" onclick="closeModal('generic-modal')">Close</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    setTimeout(() => modal.classList.add('active'), 10);
}

function showConfirmModal(title, content, onConfirm) {
    const existingModal = document.getElementById('confirm-modal');
    if (existingModal) existingModal.remove();

    const modal = document.createElement('div');
    modal.id = 'confirm-modal';
    modal.className = 'modal-backdrop';
    modal.innerHTML = `
        <div class="modal">
            <div class="modal-header">
                <h3 class="modal-title">${title}</h3>
                <button class="modal-close" onclick="closeModal('confirm-modal')">&times;</button>
            </div>
            <div class="modal-body">${content}</div>
            <div class="modal-footer">
                <button class="btn btn-secondary" onclick="closeModal('confirm-modal')">Cancel</button>
                <button class="btn btn-danger" id="confirm-action-btn">Confirm</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    document.getElementById('confirm-action-btn').onclick = onConfirm;
    setTimeout(() => modal.classList.add('active'), 10);
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('active');
        setTimeout(() => modal.remove(), 300);
    }
}

function getStatusBadge(status) {
    const badges = {
        'active': '<span class="badge badge-success">Active</span>',
        'completed': '<span class="badge badge-info">Completed</span>',
        'failed': '<span class="badge badge-danger">Failed</span>',
        'rolled_back': '<span class="badge badge-warning">Rolled Back</span>',
        'new': '<span class="badge badge-primary">New</span>',
        'qualified': '<span class="badge badge-info">Qualified</span>',
        'customer': '<span class="badge badge-success">Customer</span>',
        'lead': '<span class="badge badge-primary">Lead</span>',
        'opportunity': '<span class="badge badge-warning">Opportunity</span>'
    };
    return badges[status] || `<span class="badge">${status}</span>`;
}

function getSnapshotTypeBadge(type) {
    const badges = {
        'before': '<span class="badge badge-warning">Before</span>',
        'after': '<span class="badge badge-success">After</span>',
        'checkpoint': '<span class="badge badge-info">Checkpoint</span>'
    };
    return badges[type] || `<span class="badge">${type}</span>`;
}

function getActionMarkerClass(status) {
    const classes = {
        'completed': 'success',
        'failed': 'danger',
        'rolled_back': 'warning'
    };
    return classes[status] || '';
}

function formatDate(dateStr) {
    if (!dateStr) return 'N/A';
    const date = new Date(dateStr);
    return date.toLocaleString();
}

function formatTime(dateStr) {
    if (!dateStr) return 'N/A';
    const date = new Date(dateStr);
    return date.toLocaleTimeString();
}

function formatDuration(start, end) {
    const startDate = new Date(start);
    const endDate = new Date(end);
    const diff = endDate - startDate;
    const seconds = Math.floor(diff / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);

    if (hours > 0) return `${hours}h ${minutes % 60}m`;
    if (minutes > 0) return `${minutes}m ${seconds % 60}s`;
    return `${seconds}s`;
}

function truncateJson(obj, maxLength = 100) {
    const str = JSON.stringify(obj);
    return str.length > maxLength ? str.substring(0, maxLength) + '...' : str;
}

function addLogEntry(message, type = 'info') {
    const logContainer = document.getElementById('live-log');
    if (!logContainer) return;

    const timestamp = new Date().toLocaleTimeString();
    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;
    entry.innerHTML = `<span class="timestamp">[${timestamp}]</span> ${message}`;
    logContainer.appendChild(entry);
    logContainer.scrollTop = logContainer.scrollHeight;
}

function updateDemoStatus(status) {
    const statusEl = document.getElementById('demo-status');
    if (statusEl) {
        statusEl.innerHTML = status === 'running'
            ? '<span class="badge badge-success">Running</span>'
            : '<span class="badge badge-secondary">Stopped</span>';
    }
}

// Event Handlers
async function startDemoAgent() {
    state.demoAgent = new DemoSalesAgent();
    await state.demoAgent.start();
    loadDashboard();
}

async function stopDemoAgent() {
    if (state.demoAgent) {
        await state.demoAgent.stop();
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadDashboard();
    renderCRM();

    // Refresh dashboard periodically
    setInterval(() => {
        if (document.visibilityState === 'visible') {
            loadDashboard();
        }
    }, 10000);
});
