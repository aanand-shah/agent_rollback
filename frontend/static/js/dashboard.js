/**
 * AgentRollback Dashboard
 * Admin interface for monitoring and managing AI agent state tracking
 */

(function() {
    'use strict';

    // ============================================================
    // Configuration
    // ============================================================
    const API_BASE = window.location.origin;
    const REFRESH_INTERVAL = 10000; // 10 seconds

    // ============================================================
    // State
    // ============================================================
    const state = {
        sessions: [],
        currentSession: null,
        actions: [],
        snapshots: [],
        pendingRollback: null
    };

    // ============================================================
    // API Client
    // ============================================================
    const api = {
        async get(endpoint) {
            try {
                const response = await fetch(`${API_BASE}${endpoint}`);
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                return await response.json();
            } catch (error) {
                console.error('API GET error:', endpoint, error);
                throw error;
            }
        },

        async post(endpoint, data) {
            try {
                const response = await fetch(`${API_BASE}${endpoint}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                return await response.json();
            } catch (error) {
                console.error('API POST error:', endpoint, error);
                throw error;
            }
        },

        async delete(endpoint) {
            try {
                const response = await fetch(`${API_BASE}${endpoint}`, { method: 'DELETE' });
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                return await response.json();
            } catch (error) {
                console.error('API DELETE error:', endpoint, error);
                throw error;
            }
        }
    };

    // ============================================================
    // UI Helpers
    // ============================================================
    function $(selector) {
        return document.querySelector(selector);
    }

    function $$(selector) {
        return document.querySelectorAll(selector);
    }

    function showAlert(message, type = 'info') {
        const container = $('#alert-container');
        if (!container) return;

        const alertClass = type === 'error' ? 'alert-danger' :
                          type === 'success' ? 'alert-success' : 'alert-warning';
        const icon = type === 'error' ? 'exclamation-circle' :
                    type === 'success' ? 'check-circle' : 'info-circle';

        container.innerHTML = `
            <div class="alert ${alertClass}">
                <i class="fas fa-${icon}"></i>
                <span>${message}</span>
            </div>
        `;

        setTimeout(() => { container.innerHTML = ''; }, 5000);
    }

    function formatDate(dateStr) {
        if (!dateStr) return 'N/A';
        return new Date(dateStr).toLocaleString();
    }

    function formatTime(dateStr) {
        if (!dateStr) return 'N/A';
        return new Date(dateStr).toLocaleTimeString();
    }

    function formatDuration(start, end) {
        if (!start) return '-';
        const startDate = new Date(start);
        const endDate = end ? new Date(end) : new Date();
        const diff = endDate - startDate;
        const seconds = Math.floor(diff / 1000);
        const minutes = Math.floor(seconds / 60);
        const hours = Math.floor(minutes / 60);

        if (hours > 0) return `${hours}h ${minutes % 60}m`;
        if (minutes > 0) return `${minutes}m ${seconds % 60}s`;
        return `${seconds}s`;
    }

    function getStatusBadge(status) {
        const badges = {
            'active': '<span class="badge badge-success">Active</span>',
            'completed': '<span class="badge badge-info">Completed</span>',
            'failed': '<span class="badge badge-danger">Failed</span>',
            'rolled_back': '<span class="badge badge-warning">Rolled Back</span>'
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

    // ============================================================
    // Modal Management
    // ============================================================
    function openModal(modalId) {
        const modal = $(`#${modalId}`);
        if (modal) {
            modal.classList.add('active');
        }
    }

    function closeModal(modalId) {
        const modal = $(`#${modalId}`);
        if (modal) {
            modal.classList.remove('active');
        }
    }

    // ============================================================
    // Page Navigation
    // ============================================================
    function showPage(pageId) {
        $$('.page').forEach(p => p.classList.remove('active'));
        $$('.sidebar-nav-link').forEach(l => l.classList.remove('active'));

        const page = $(`#page-${pageId}`);
        const link = $(`.sidebar-nav-link[data-page="${pageId}"]`);

        if (page) page.classList.add('active');
        if (link) link.classList.add('active');
    }

    // ============================================================
    // Data Loading
    // ============================================================
    async function loadDashboard() {
        try {
            const data = await api.get('/api/v1/sessions?limit=100');
            state.sessions = data.sessions || [];
            renderStats();
            renderSessionsTable();
            updateConnectionStatus(true);
        } catch (error) {
            showAlert('Failed to load dashboard: ' + error.message, 'error');
            updateConnectionStatus(false);
        }
    }

    function updateConnectionStatus(connected) {
        const el = $('#connection-status');
        if (el) {
            el.innerHTML = connected
                ? '<span class="badge badge-success">Connected</span>'
                : '<span class="badge badge-danger">Disconnected</span>';
        }
    }

    function renderStats() {
        const active = state.sessions.filter(s => s.status === 'active').length;
        const completed = state.sessions.filter(s => s.status === 'completed').length;
        const failed = state.sessions.filter(s => s.status === 'failed').length;
        const rolledBack = state.sessions.filter(s => s.status === 'rolled_back').length;

        const statActive = $('#stat-active');
        const statCompleted = $('#stat-completed');
        const statFailed = $('#stat-failed');
        const statRollbacks = $('#stat-rollbacks');
        const sessionCount = $('#session-count');

        if (statActive) statActive.textContent = active;
        if (statCompleted) statCompleted.textContent = completed;
        if (statFailed) statFailed.textContent = failed;
        if (statRollbacks) statRollbacks.textContent = rolledBack;
        if (sessionCount) sessionCount.textContent = `${state.sessions.length} sessions`;
    }

    function renderSessionsTable(targetId = 'sessions-tbody') {
        const tbody = $(`#${targetId}`);
        if (!tbody) return;

        if (state.sessions.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" class="empty-state">
                        <div class="empty-state-icon">📭</div>
                        <p>No sessions yet. Start the Demo App to create some!</p>
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = state.sessions.map(session => `
            <tr class="clickable-row" data-session-id="${session.id}">
                <td><code class="mono">${session.id.substring(0, 8)}...</code></td>
                <td>${escapeHtml(session.agent_id)}</td>
                <td>${getStatusBadge(session.status)}</td>
                <td>${formatDate(session.started_at)}</td>
                <td>${formatDuration(session.started_at, session.ended_at)}${!session.ended_at ? ' <span class="badge badge-success">Live</span>' : ''}</td>
                <td>
                    <div class="action-buttons">
                        <button class="btn btn-sm btn-secondary view-session-btn" data-session-id="${session.id}">
                            <i class="fas fa-eye"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');

        // Add click handlers
        tbody.querySelectorAll('.clickable-row').forEach(row => {
            row.addEventListener('click', (e) => {
                if (!e.target.closest('button')) {
                    viewSession(row.dataset.sessionId);
                }
            });
        });

        tbody.querySelectorAll('.view-session-btn').forEach(btn => {
            btn.addEventListener('click', () => viewSession(btn.dataset.sessionId));
        });
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ============================================================
    // Session Detail View
    // ============================================================
    async function viewSession(sessionId) {
        try {
            state.currentSession = sessionId;

            const [sessionData, actionsData, snapshotsData] = await Promise.all([
                api.get(`/api/v1/sessions/${sessionId}`),
                api.get(`/api/v1/sessions/${sessionId}/actions?limit=100`),
                api.get(`/api/v1/sessions/${sessionId}/snapshots?limit=100`)
            ]);

            state.actions = actionsData.actions || [];
            state.snapshots = snapshotsData.snapshots || [];

            renderSessionModal(sessionData.session);
            openModal('session-modal');
        } catch (error) {
            showAlert('Failed to load session: ' + error.message, 'error');
        }
    }

    function renderSessionModal(session) {
        $('#modal-session-id').textContent = session.id;
        $('#modal-agent-id').textContent = session.agent_id;
        $('#modal-session-status').innerHTML = getStatusBadge(session.status);
        $('#modal-started-at').textContent = formatDate(session.started_at);
        $('#modal-ended-at').textContent = session.ended_at ? formatDate(session.ended_at) : 'Active';

        renderTimeline();
        renderSnapshotsList();
    }

    function renderTimeline() {
        const container = $('#timeline-container');
        if (!container) return;

        if (state.actions.length === 0) {
            container.innerHTML = '<div class="empty-state">No actions recorded</div>';
            return;
        }

        container.innerHTML = `
            <div class="timeline">
                ${state.actions.map(action => `
                    <div class="timeline-item">
                        <div class="timeline-marker ${action.status === 'completed' ? 'success' : action.status === 'failed' ? 'danger' : ''}"></div>
                        <div class="timeline-content">
                            <div class="timeline-time">${formatTime(action.executed_at)}</div>
                            <div class="timeline-title">${escapeHtml(action.action_type)}</div>
                            ${action.action_data ? `
                                <div class="timeline-description">
                                    ${escapeHtml(JSON.stringify(action.action_data).substring(0, 100))}...
                                </div>
                            ` : ''}
                            <div style="margin-top: 0.5rem;">
                                ${action.before_snapshot_id ? `
                                    <button class="btn btn-sm btn-secondary view-snapshot-btn" data-snapshot-id="${action.before_snapshot_id}">
                                        Before
                                    </button>
                                ` : ''}
                                ${action.after_snapshot_id ? `
                                    <button class="btn btn-sm btn-secondary view-snapshot-btn" data-snapshot-id="${action.after_snapshot_id}">
                                        After
                                    </button>
                                ` : ''}
                            </div>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;

        container.querySelectorAll('.view-snapshot-btn').forEach(btn => {
            btn.addEventListener('click', () => viewSnapshot(btn.dataset.snapshotId));
        });
    }

    function renderSnapshotsList() {
        const container = $('#snapshots-list');
        if (!container) return;

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
                        <button class="btn btn-sm btn-secondary view-snapshot-btn" data-snapshot-id="${snapshot.id}">
                            <i class="fas fa-eye"></i> View
                        </button>
                        <button class="btn btn-sm btn-warning rollback-btn" data-snapshot-id="${snapshot.id}">
                            <i class="fas fa-undo"></i> Rollback
                        </button>
                    </div>
                </div>
            </div>
        `).join('');

        container.querySelectorAll('.view-snapshot-btn').forEach(btn => {
            btn.addEventListener('click', () => viewSnapshot(btn.dataset.snapshotId));
        });

        container.querySelectorAll('.rollback-btn').forEach(btn => {
            btn.addEventListener('click', () => confirmRollback(btn.dataset.snapshotId));
        });
    }

    // ============================================================
    // Snapshot View
    // ============================================================
    async function viewSnapshot(snapshotId) {
        try {
            const data = await api.get(`/api/v1/snapshots/${snapshotId}`);
            const snapshot = data.snapshot;

            const body = $('#snapshot-modal-body');
            body.innerHTML = `
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
                    <pre class="json-view">${escapeHtml(JSON.stringify(snapshot.state_data, null, 2))}</pre>
                </div>
            `;

            openModal('snapshot-modal');
        } catch (error) {
            showAlert('Failed to load snapshot: ' + error.message, 'error');
        }
    }

    // ============================================================
    // Rollback
    // ============================================================
    async function confirmRollback(snapshotId) {
        if (!state.currentSession) return;

        try {
            const preview = await api.get(`/api/v1/rollback/preview?session_id=${state.currentSession}&target_snapshot_id=${snapshotId}`);

            state.pendingRollback = { sessionId: state.currentSession, snapshotId };

            const body = $('#rollback-modal-body');
            body.innerHTML = `
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

            openModal('rollback-modal');
        } catch (error) {
            showAlert('Failed to preview rollback: ' + error.message, 'error');
        }
    }

    async function executeRollback() {
        if (!state.pendingRollback) return;

        try {
            // First, get the snapshot data we're rolling back to
            const snapshotData = await api.get(`/api/v1/snapshots/${state.pendingRollback.snapshotId}`);
            const snapshot = snapshotData.snapshot;

            // Execute rollback in AgentRollback
            const result = await api.post('/api/v1/rollback', {
                session_id: state.pendingRollback.sessionId,
                target_snapshot_id: state.pendingRollback.snapshotId,
                dry_run: false
            });

            if (result.success) {
                // Notify the Demo CRM app to restore its state
                try {
                    await fetch('http://localhost:8001/api/restore-state', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ state_data: snapshot.state_data })
                    });
                } catch (crmError) {
                    console.warn('Could not notify CRM app (may not be running):', crmError);
                }

                showAlert(`Rollback successful! Reverted ${result.actions_reverted} actions. Refresh the Demo CRM to see changes.`, 'success');
                closeModal('rollback-modal');
                closeModal('session-modal');
                loadDashboard();
            } else {
                showAlert('Rollback failed: ' + result.errors.join(', '), 'error');
            }
        } catch (error) {
            showAlert('Rollback failed: ' + error.message, 'error');
        }

        state.pendingRollback = null;
    }

    // ============================================================
    // Event Handlers
    // ============================================================
    function setupEventListeners() {
        // Navigation
        $$('.sidebar-nav-link[data-page]').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                showPage(link.dataset.page);
            });
        });

        // Refresh buttons
        const refreshBtn = $('#refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', loadDashboard);
        }

        const refreshSessionsBtn = $('#refresh-sessions-btn');
        if (refreshSessionsBtn) {
            refreshSessionsBtn.addEventListener('click', loadDashboard);
        }

        // Status filter
        const statusFilter = $('#status-filter');
        if (statusFilter) {
            statusFilter.addEventListener('change', async () => {
                const status = statusFilter.value;
                try {
                    let url = '/api/v1/sessions?limit=100';
                    if (status) url += `&status=${status}`;
                    const data = await api.get(url);
                    state.sessions = data.sessions || [];
                    renderStats();
                    renderSessionsTable();
                    renderSessionsTable('all-sessions-tbody');
                } catch (error) {
                    showAlert('Failed to filter sessions: ' + error.message, 'error');
                }
            });
        }

        // Modal close buttons
        const closeSessionModal = $('#close-session-modal');
        const closeModalBtn = $('#close-modal-btn');
        if (closeSessionModal) closeSessionModal.addEventListener('click', () => closeModal('session-modal'));
        if (closeModalBtn) closeModalBtn.addEventListener('click', () => closeModal('session-modal'));

        const closeRollbackModal = $('#close-rollback-modal');
        const cancelRollbackBtn = $('#cancel-rollback-btn');
        if (closeRollbackModal) closeRollbackModal.addEventListener('click', () => closeModal('rollback-modal'));
        if (cancelRollbackBtn) cancelRollbackBtn.addEventListener('click', () => closeModal('rollback-modal'));

        const confirmRollbackBtn = $('#confirm-rollback-btn');
        if (confirmRollbackBtn) confirmRollbackBtn.addEventListener('click', executeRollback);

        const closeSnapshotModal = $('#close-snapshot-modal');
        const closeSnapshotBtn = $('#close-snapshot-btn');
        if (closeSnapshotModal) closeSnapshotModal.addEventListener('click', () => closeModal('snapshot-modal'));
        if (closeSnapshotBtn) closeSnapshotBtn.addEventListener('click', () => closeModal('snapshot-modal'));

        // Tab navigation
        $$('.tab[data-tab]').forEach(tab => {
            tab.addEventListener('click', () => {
                $$('.tab').forEach(t => t.classList.remove('active'));
                $$('.tab-content').forEach(c => c.style.display = 'none');

                tab.classList.add('active');
                const content = $(`#tab-${tab.dataset.tab}`);
                if (content) content.style.display = 'block';
            });
        });

        // Close modals on backdrop click
        $$('.modal-backdrop').forEach(modal => {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    modal.classList.remove('active');
                }
            });
        });
    }

    // ============================================================
    // Initialization
    // ============================================================
    function init() {
        setupEventListeners();
        loadDashboard();

        // Auto-refresh
        setInterval(() => {
            if (document.visibilityState === 'visible') {
                loadDashboard();
            }
        }, REFRESH_INTERVAL);
    }

    // Start when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
