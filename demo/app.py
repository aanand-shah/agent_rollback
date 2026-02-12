"""
Demo CRM Application with AgentRollback Integration

This is a standalone AI-powered CRM application that demonstrates
how to integrate AgentRollback into a real application.

Runs on port 8001 and connects to AgentRollback server on port 8000.
"""

import json
import random
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel


# ============================================================
# Configuration
# ============================================================
AGENTROLLBACK_URL = "http://localhost:8000"
AGENT_ID = "ai-sales-agent"


# ============================================================
# CRM Data Models
# ============================================================
class Lead(BaseModel):
    id: str
    company: str
    contact_name: str
    email: str
    value: float
    status: str = "new"
    score: int = 0


class CRMState(BaseModel):
    leads: dict[str, dict] = {}
    opportunities: dict[str, dict] = {}
    customers: dict[str, dict] = {}
    revenue: float = 0


# ============================================================
# Global State
# ============================================================
crm_state = CRMState()
session_id: Optional[str] = None
http_client: Optional[httpx.AsyncClient] = None


# ============================================================
# AgentRollback Integration
# ============================================================
async def start_tracking_session():
    """Start a new tracking session with AgentRollback."""
    global session_id
    try:
        response = await http_client.post(
            f"{AGENTROLLBACK_URL}/api/v1/sessions",
            json={"agent_id": AGENT_ID, "metadata": {"app": "demo-crm"}}
        )
        response.raise_for_status()
        data = response.json()
        session_id = data["session"]["id"]
        return session_id
    except Exception as e:
        print(f"Failed to start tracking session: {e}")
        return None


async def end_tracking_session():
    """End the current tracking session."""
    global session_id
    if not session_id:
        return
    try:
        await http_client.delete(
            f"{AGENTROLLBACK_URL}/api/v1/sessions/{session_id}",
            params={"status": "completed"}
        )
    except Exception as e:
        print(f"Failed to end tracking session: {e}")
    session_id = None


async def record_action(action_type: str, action_data: dict, before_state: dict, after_state: dict):
    """Record an action with AgentRollback."""
    if not session_id:
        return
    try:
        await http_client.post(
            f"{AGENTROLLBACK_URL}/api/v1/sessions/{session_id}/actions",
            json={
                "session_id": session_id,
                "action_type": action_type,
                "action_data": action_data,
                "before_state": before_state,
                "after_state": after_state,
                "connector_type": "crm"
            }
        )
    except Exception as e:
        print(f"Failed to record action: {e}")


async def create_checkpoint():
    """Create a checkpoint with AgentRollback."""
    if not session_id:
        return None
    try:
        response = await http_client.post(
            f"{AGENTROLLBACK_URL}/api/v1/sessions/{session_id}/checkpoint",
            json={
                "connector_type": "crm",
                "state_data": crm_state.model_dump()
            }
        )
        response.raise_for_status()
        return response.json()["snapshot"]["id"]
    except Exception as e:
        print(f"Failed to create checkpoint: {e}")
        return None


# ============================================================
# FastAPI App
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient(timeout=30.0)
    reset_crm()
    yield
    if session_id:
        await end_tracking_session()
    await http_client.aclose()


app = FastAPI(
    title="Demo CRM Application",
    description="AI-powered CRM with AgentRollback integration",
    lifespan=lifespan
)

# Add CORS middleware to allow dashboard to call restore-state
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# CRM Helper Functions
# ============================================================
def reset_crm():
    """Reset CRM to initial state with sample data."""
    global crm_state
    crm_state = CRMState(
        leads={
            "L001": {"id": "L001", "company": "Acme Corp", "contact_name": "John Smith",
                    "email": "john@acme.com", "value": 50000, "status": "new", "score": 0},
            "L002": {"id": "L002", "company": "TechStart Inc", "contact_name": "Jane Doe",
                    "email": "jane@techstart.io", "value": 75000, "status": "new", "score": 0},
            "L003": {"id": "L003", "company": "Global Systems", "contact_name": "Bob Wilson",
                    "email": "bob@globalsys.com", "value": 120000, "status": "new", "score": 0},
        },
        opportunities={},
        customers={},
        revenue=0
    )


def get_state_dict() -> dict:
    """Get current state as dictionary."""
    return crm_state.model_dump()


# ============================================================
# API Endpoints
# ============================================================
@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the demo CRM UI."""
    return DEMO_HTML


@app.get("/api/state")
async def get_state():
    """Get current CRM state."""
    return {
        "state": get_state_dict(),
        "session_id": session_id,
        "tracking": session_id is not None
    }


@app.post("/api/start-session")
async def api_start_session():
    """Start a new AgentRollback tracking session."""
    sid = await start_tracking_session()
    if sid:
        return {"success": True, "session_id": sid}
    raise HTTPException(500, "Failed to start session. Is AgentRollback server running?")


@app.post("/api/end-session")
async def api_end_session():
    """End the current tracking session."""
    await end_tracking_session()
    return {"success": True}


@app.post("/api/checkpoint")
async def api_checkpoint():
    """Create a checkpoint."""
    checkpoint_id = await create_checkpoint()
    if checkpoint_id:
        return {"success": True, "checkpoint_id": checkpoint_id}
    raise HTTPException(500, "Failed to create checkpoint")


@app.post("/api/reset")
async def api_reset():
    """Reset CRM data."""
    reset_crm()
    return {"success": True, "state": get_state_dict()}


@app.post("/api/qualify-lead")
async def qualify_lead():
    """AI qualifies the next available lead."""
    before = get_state_dict()

    # Find a lead to qualify
    lead_id = None
    for lid, lead in crm_state.leads.items():
        if lead["status"] == "new":
            lead_id = lid
            break

    if not lead_id:
        raise HTTPException(400, "No leads to qualify")

    lead = crm_state.leads[lead_id]

    # AI scoring logic
    score = random.randint(30, 100)
    lead["score"] = score

    if score >= 60:
        lead["status"] = "qualified"
        result = "qualified"
    else:
        lead["status"] = "disqualified"
        result = "disqualified"

    after = get_state_dict()
    await record_action("qualify_lead", {"lead_id": lead_id, "score": score, "result": result}, before, after)

    return {"success": True, "lead_id": lead_id, "score": score, "result": result, "state": after}


@app.post("/api/convert-opportunity")
async def convert_opportunity():
    """Convert a qualified lead to an opportunity."""
    before = get_state_dict()

    # Find a qualified lead
    lead_id = None
    for lid, lead in crm_state.leads.items():
        if lead["status"] == "qualified":
            lead_id = lid
            break

    if not lead_id:
        raise HTTPException(400, "No qualified leads to convert")

    lead = crm_state.leads[lead_id]
    opp_id = f"OPP-{len(crm_state.opportunities) + 1:03d}"

    crm_state.opportunities[opp_id] = {
        "id": opp_id,
        "company": lead["company"],
        "contact_name": lead["contact_name"],
        "value": lead["value"],
        "stage": "proposal",
        "lead_id": lead_id
    }

    lead["status"] = "converted"

    after = get_state_dict()
    await record_action("convert_opportunity", {"lead_id": lead_id, "opportunity_id": opp_id}, before, after)

    return {"success": True, "opportunity_id": opp_id, "state": after}


@app.post("/api/close-deal")
async def close_deal():
    """Close an opportunity as won."""
    before = get_state_dict()

    # Find an opportunity to close
    opp_id = None
    for oid, opp in crm_state.opportunities.items():
        if opp["stage"] == "proposal":
            opp_id = oid
            break

    if not opp_id:
        raise HTTPException(400, "No opportunities to close")

    opp = crm_state.opportunities[opp_id]

    # Move to customers
    customer_id = f"CUST-{len(crm_state.customers) + 1:03d}"
    crm_state.customers[customer_id] = {
        "id": customer_id,
        "company": opp["company"],
        "contact_name": opp["contact_name"],
        "value": opp["value"],
        "opportunity_id": opp_id
    }

    crm_state.revenue += opp["value"]
    opp["stage"] = "closed_won"

    after = get_state_dict()
    await record_action("close_deal", {"opportunity_id": opp_id, "customer_id": customer_id, "value": opp["value"]}, before, after)

    return {"success": True, "customer_id": customer_id, "value": opp["value"], "state": after}


@app.post("/api/simulate-error")
async def simulate_error():
    """Simulate an AI error that corrupts data."""
    before = get_state_dict()

    # Corrupt the data
    crm_state.leads.clear()
    crm_state.opportunities.clear()
    crm_state.customers.clear()
    crm_state.revenue = -99999

    after = get_state_dict()
    await record_action("error_data_corruption", {"error": "Simulated AI failure"}, before, after)

    return {"success": True, "message": "Data corrupted!", "state": after}


@app.post("/api/restore-state")
async def restore_state(request: Request):
    """Restore CRM state from a snapshot (called after rollback)."""
    global crm_state
    body = await request.json()
    state_data = body.get("state_data", {})

    crm_state = CRMState(
        leads=state_data.get("leads", {}),
        opportunities=state_data.get("opportunities", {}),
        customers=state_data.get("customers", {}),
        revenue=state_data.get("revenue", 0)
    )

    return {"success": True, "state": get_state_dict()}


# ============================================================
# HTML Template
# ============================================================
DEMO_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Demo CRM - AI Sales Agent</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary: #6366f1;
            --primary-dark: #4f46e5;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --info: #3b82f6;
            --gray-100: #f3f4f6;
            --gray-200: #e5e7eb;
            --gray-300: #d1d5db;
            --gray-500: #6b7280;
            --gray-700: #374151;
            --gray-800: #1f2937;
            --gray-900: #111827;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Inter', sans-serif;
            background: var(--gray-100);
            color: var(--gray-800);
            line-height: 1.6;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
        }

        header {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            padding: 2rem;
            margin-bottom: 2rem;
            border-radius: 12px;
        }

        header h1 {
            font-size: 1.75rem;
            margin-bottom: 0.5rem;
        }

        header p {
            opacity: 0.9;
        }

        .tracking-status {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            margin-top: 1rem;
            padding: 0.5rem 1rem;
            background: rgba(255,255,255,0.2);
            border-radius: 20px;
            font-size: 0.875rem;
        }

        .tracking-status.active { background: rgba(16, 185, 129, 0.3); }
        .tracking-status.inactive { background: rgba(239, 68, 68, 0.3); }

        .controls {
            display: flex;
            gap: 1rem;
            flex-wrap: wrap;
            margin-bottom: 2rem;
        }

        .btn {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.75rem 1.25rem;
            border-radius: 8px;
            font-size: 0.875rem;
            font-weight: 600;
            cursor: pointer;
            border: none;
            transition: all 0.2s;
        }

        .btn-primary { background: var(--primary); color: white; }
        .btn-primary:hover { background: var(--primary-dark); }
        .btn-success { background: var(--success); color: white; }
        .btn-success:hover { background: #059669; }
        .btn-warning { background: var(--warning); color: white; }
        .btn-warning:hover { background: #d97706; }
        .btn-danger { background: var(--danger); color: white; }
        .btn-danger:hover { background: #dc2626; }
        .btn-secondary { background: var(--gray-200); color: var(--gray-700); }
        .btn-secondary:hover { background: var(--gray-300); }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }

        .stat-card {
            background: white;
            border-radius: 10px;
            padding: 1.25rem;
            text-align: center;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }

        .stat-value {
            font-size: 2rem;
            font-weight: 700;
            color: var(--gray-900);
        }

        .stat-label {
            color: var(--gray-500);
            font-size: 0.875rem;
        }

        .card {
            background: white;
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }

        .card-title {
            font-size: 1.125rem;
            font-weight: 600;
            margin-bottom: 1rem;
            padding-bottom: 0.75rem;
            border-bottom: 1px solid var(--gray-200);
        }

        .data-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 1rem;
        }

        .data-card {
            background: var(--gray-100);
            border-radius: 8px;
            padding: 1rem;
            border-left: 4px solid var(--primary);
        }

        .data-card.lead { border-left-color: var(--info); }
        .data-card.opportunity { border-left-color: var(--warning); }
        .data-card.customer { border-left-color: var(--success); }

        .data-card-title {
            font-weight: 600;
            margin-bottom: 0.25rem;
        }

        .data-card-meta {
            font-size: 0.8125rem;
            color: var(--gray-500);
        }

        .data-card-value {
            font-size: 1.125rem;
            font-weight: 700;
            color: var(--success);
            margin-top: 0.5rem;
        }

        .badge {
            display: inline-block;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
        }

        .badge-new { background: var(--info); color: white; }
        .badge-qualified { background: var(--success); color: white; }
        .badge-disqualified { background: var(--gray-500); color: white; }
        .badge-converted { background: var(--warning); color: white; }

        .log {
            background: var(--gray-900);
            border-radius: 8px;
            padding: 1rem;
            max-height: 200px;
            overflow-y: auto;
            font-family: monospace;
            font-size: 0.8125rem;
        }

        .log-entry {
            padding: 0.25rem 0;
            color: var(--gray-300);
        }

        .log-entry.success { color: var(--success); }
        .log-entry.error { color: var(--danger); }
        .log-entry.info { color: var(--info); }

        .two-column {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 1.5rem;
        }

        @media (max-width: 900px) {
            .two-column { grid-template-columns: 1fr; }
        }

        .empty-state {
            text-align: center;
            padding: 2rem;
            color: var(--gray-500);
        }

        .alert {
            padding: 1rem;
            border-radius: 8px;
            margin-bottom: 1rem;
        }

        .alert-success { background: rgba(16, 185, 129, 0.1); color: var(--success); border: 1px solid var(--success); }
        .alert-danger { background: rgba(239, 68, 68, 0.1); color: var(--danger); border: 1px solid var(--danger); }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1><i class="fas fa-robot"></i> AI Sales Agent - Demo CRM</h1>
            <p>This demo shows how an AI-powered CRM integrates with AgentRollback for state recovery.</p>
            <div id="tracking-status" class="tracking-status inactive">
                <i class="fas fa-circle"></i>
                <span>Not Tracking</span>
            </div>
        </header>

        <div id="alert-container"></div>

        <div class="controls">
            <button class="btn btn-primary" id="btn-start" onclick="startSession()">
                <i class="fas fa-play"></i> Start Tracking
            </button>
            <button class="btn btn-secondary" id="btn-stop" onclick="stopSession()" disabled>
                <i class="fas fa-stop"></i> Stop Tracking
            </button>
            <button class="btn btn-success" id="btn-checkpoint" onclick="createCheckpoint()" disabled>
                <i class="fas fa-save"></i> Create Checkpoint
            </button>
            <button class="btn btn-secondary" onclick="resetCRM()">
                <i class="fas fa-redo"></i> Reset Data
            </button>
            <a href="http://localhost:8000" target="_blank" class="btn btn-secondary">
                <i class="fas fa-external-link-alt"></i> Open Dashboard
            </a>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value" id="stat-leads">0</div>
                <div class="stat-label">Leads</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="stat-opportunities">0</div>
                <div class="stat-label">Opportunities</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="stat-customers">0</div>
                <div class="stat-label">Customers</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="stat-revenue">$0</div>
                <div class="stat-label">Revenue</div>
            </div>
        </div>

        <div class="card">
            <h3 class="card-title"><i class="fas fa-magic"></i> AI Agent Actions</h3>
            <p style="margin-bottom: 1rem; color: var(--gray-500);">
                Simulate AI agent operations. Each action is tracked and can be rolled back from the Dashboard.
            </p>
            <div class="controls" style="margin-bottom: 0;">
                <button class="btn btn-primary" onclick="qualifyLead()">
                    <i class="fas fa-user-check"></i> Qualify Lead
                </button>
                <button class="btn btn-success" onclick="convertOpportunity()">
                    <i class="fas fa-handshake"></i> Convert to Opportunity
                </button>
                <button class="btn btn-warning" onclick="closeDeal()">
                    <i class="fas fa-dollar-sign"></i> Close Deal
                </button>
                <button class="btn btn-danger" onclick="simulateError()">
                    <i class="fas fa-bug"></i> Simulate Error
                </button>
            </div>
        </div>

        <div class="two-column">
            <div>
                <div class="card">
                    <h3 class="card-title"><i class="fas fa-users"></i> Leads</h3>
                    <div id="leads-container" class="data-grid">
                        <div class="empty-state">No leads</div>
                    </div>
                </div>

                <div class="card">
                    <h3 class="card-title"><i class="fas fa-chart-line"></i> Opportunities</h3>
                    <div id="opportunities-container" class="data-grid">
                        <div class="empty-state">No opportunities</div>
                    </div>
                </div>

                <div class="card">
                    <h3 class="card-title"><i class="fas fa-star"></i> Customers</h3>
                    <div id="customers-container" class="data-grid">
                        <div class="empty-state">No customers</div>
                    </div>
                </div>
            </div>

            <div>
                <div class="card">
                    <h3 class="card-title"><i class="fas fa-terminal"></i> Activity Log</h3>
                    <div class="log" id="log">
                        <div class="log-entry info">[Ready] Waiting for actions...</div>
                    </div>
                </div>

                <div class="card">
                    <h3 class="card-title"><i class="fas fa-info-circle"></i> How to Use</h3>
                    <ol style="padding-left: 1.25rem; color: var(--gray-500); font-size: 0.875rem;">
                        <li style="margin-bottom: 0.5rem;"><strong>Start Tracking</strong> - Begin recording actions</li>
                        <li style="margin-bottom: 0.5rem;"><strong>Perform Actions</strong> - Use the AI agent buttons</li>
                        <li style="margin-bottom: 0.5rem;"><strong>Create Checkpoint</strong> - Save a recovery point</li>
                        <li style="margin-bottom: 0.5rem;"><strong>Simulate Error</strong> - Corrupt the data</li>
                        <li style="margin-bottom: 0.5rem;"><strong>Open Dashboard</strong> - Rollback from there!</li>
                    </ol>
                </div>
            </div>
        </div>
    </div>

    <script>
        let isTracking = false;

        function log(message, type = 'info') {
            const logEl = document.getElementById('log');
            const time = new Date().toLocaleTimeString();
            const entry = document.createElement('div');
            entry.className = 'log-entry ' + type;
            entry.textContent = `[${time}] ${message}`;
            logEl.appendChild(entry);
            logEl.scrollTop = logEl.scrollHeight;
        }

        function showAlert(message, type) {
            const container = document.getElementById('alert-container');
            container.innerHTML = `<div class="alert alert-${type}">${message}</div>`;
            setTimeout(() => container.innerHTML = '', 5000);
        }

        function updateUI(state) {
            const { leads, opportunities, customers, revenue } = state;

            document.getElementById('stat-leads').textContent = Object.keys(leads).length;
            document.getElementById('stat-opportunities').textContent = Object.keys(opportunities).length;
            document.getElementById('stat-customers').textContent = Object.keys(customers).length;
            document.getElementById('stat-revenue').textContent = '$' + revenue.toLocaleString();

            // Leads
            const leadsContainer = document.getElementById('leads-container');
            const leadsHtml = Object.values(leads).map(l => `
                <div class="data-card lead">
                    <div class="data-card-title">${l.company}</div>
                    <div class="data-card-meta">${l.contact_name}</div>
                    <span class="badge badge-${l.status}">${l.status}</span>
                    ${l.score > 0 ? `<span style="margin-left: 0.5rem;">Score: ${l.score}</span>` : ''}
                    <div class="data-card-value">$${l.value.toLocaleString()}</div>
                </div>
            `).join('');
            leadsContainer.innerHTML = leadsHtml || '<div class="empty-state">No leads</div>';

            // Opportunities
            const oppsContainer = document.getElementById('opportunities-container');
            const oppsHtml = Object.values(opportunities).map(o => `
                <div class="data-card opportunity">
                    <div class="data-card-title">${o.company}</div>
                    <div class="data-card-meta">${o.contact_name} - ${o.stage}</div>
                    <div class="data-card-value">$${o.value.toLocaleString()}</div>
                </div>
            `).join('');
            oppsContainer.innerHTML = oppsHtml || '<div class="empty-state">No opportunities</div>';

            // Customers
            const custContainer = document.getElementById('customers-container');
            const custHtml = Object.values(customers).map(c => `
                <div class="data-card customer">
                    <div class="data-card-title">${c.company}</div>
                    <div class="data-card-meta">${c.contact_name}</div>
                    <div class="data-card-value">$${c.value.toLocaleString()}</div>
                </div>
            `).join('');
            custContainer.innerHTML = custHtml || '<div class="empty-state">No customers</div>';
        }

        function updateTrackingStatus(tracking) {
            isTracking = tracking;
            const statusEl = document.getElementById('tracking-status');
            statusEl.className = 'tracking-status ' + (tracking ? 'active' : 'inactive');
            statusEl.innerHTML = tracking
                ? '<i class="fas fa-circle"></i><span>Recording Actions</span>'
                : '<i class="fas fa-circle"></i><span>Not Tracking</span>';

            document.getElementById('btn-start').disabled = tracking;
            document.getElementById('btn-stop').disabled = !tracking;
            document.getElementById('btn-checkpoint').disabled = !tracking;
        }

        async function loadState() {
            try {
                const response = await fetch('/api/state');
                const data = await response.json();
                updateUI(data.state);
                updateTrackingStatus(data.tracking);
            } catch (error) {
                log('Failed to load state: ' + error.message, 'error');
            }
        }

        async function startSession() {
            try {
                const response = await fetch('/api/start-session', { method: 'POST' });
                const data = await response.json();
                if (data.success) {
                    updateTrackingStatus(true);
                    log('Started tracking session: ' + data.session_id.substring(0, 8) + '...', 'success');
                }
            } catch (error) {
                showAlert('Failed to start session. Is AgentRollback server running on port 8000?', 'danger');
                log('Failed to start session: ' + error.message, 'error');
            }
        }

        async function stopSession() {
            try {
                await fetch('/api/end-session', { method: 'POST' });
                updateTrackingStatus(false);
                log('Stopped tracking session', 'info');
            } catch (error) {
                log('Failed to stop session: ' + error.message, 'error');
            }
        }

        async function createCheckpoint() {
            try {
                const response = await fetch('/api/checkpoint', { method: 'POST' });
                const data = await response.json();
                if (data.success) {
                    log('Checkpoint created: ' + data.checkpoint_id.substring(0, 8) + '...', 'success');
                    showAlert('Checkpoint created! You can rollback to this point from the Dashboard.', 'success');
                }
            } catch (error) {
                log('Failed to create checkpoint: ' + error.message, 'error');
            }
        }

        async function resetCRM() {
            try {
                const response = await fetch('/api/reset', { method: 'POST' });
                const data = await response.json();
                updateUI(data.state);
                log('CRM data reset to initial state', 'info');
            } catch (error) {
                log('Failed to reset: ' + error.message, 'error');
            }
        }

        async function qualifyLead() {
            try {
                const response = await fetch('/api/qualify-lead', { method: 'POST' });
                if (!response.ok) {
                    const err = await response.json();
                    throw new Error(err.detail);
                }
                const data = await response.json();
                updateUI(data.state);
                log(`Lead ${data.lead_id} ${data.result} (score: ${data.score})`, data.result === 'qualified' ? 'success' : 'info');
            } catch (error) {
                log('Qualify lead failed: ' + error.message, 'error');
            }
        }

        async function convertOpportunity() {
            try {
                const response = await fetch('/api/convert-opportunity', { method: 'POST' });
                if (!response.ok) {
                    const err = await response.json();
                    throw new Error(err.detail);
                }
                const data = await response.json();
                updateUI(data.state);
                log(`Created opportunity ${data.opportunity_id}`, 'success');
            } catch (error) {
                log('Convert failed: ' + error.message, 'error');
            }
        }

        async function closeDeal() {
            try {
                const response = await fetch('/api/close-deal', { method: 'POST' });
                if (!response.ok) {
                    const err = await response.json();
                    throw new Error(err.detail);
                }
                const data = await response.json();
                updateUI(data.state);
                log(`Closed deal! Customer ${data.customer_id}, revenue +$${data.value.toLocaleString()}`, 'success');
            } catch (error) {
                log('Close deal failed: ' + error.message, 'error');
            }
        }

        async function simulateError() {
            try {
                const response = await fetch('/api/simulate-error', { method: 'POST' });
                const data = await response.json();
                updateUI(data.state);
                log('ERROR: Data corrupted! Go to Dashboard to rollback.', 'error');
                showAlert('Data corrupted! Open the AgentRollback Dashboard to rollback to a checkpoint.', 'danger');
            } catch (error) {
                log('Simulate error failed: ' + error.message, 'error');
            }
        }

        // Initialize
        loadState();

        // Auto-refresh when window regains focus (catches rollback changes)
        window.addEventListener('focus', loadState);

        // Poll for state changes every 5 seconds
        setInterval(loadState, 5000);
    </script>
</body>
</html>
"""


def run_demo_app(host: str = "127.0.0.1", port: int = 8001):
    """Run the demo CRM application."""
    import uvicorn

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║              Demo CRM Application                            ║
╠══════════════════════════════════════════════════════════════╣
║  Demo App:      http://{host}:{port}/
║  Dashboard:     http://localhost:8000/
║
║  Make sure AgentRollback server is running on port 8000!
╚══════════════════════════════════════════════════════════════╝
""")

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_demo_app()
