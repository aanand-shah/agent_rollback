"""
Combined FastAPI server with frontend dashboard.

This module extends the base AgentRollback API server to also serve
the web-based dashboard interface.
"""

import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

# Import the base API app components
from agent_rollback.server import (
    app as base_app,
    _store,
    _tracker,
    _recovery,
)
from agent_rollback.store import StateStore
from agent_rollback.tracker import StateTracker
from agent_rollback.recovery import RecoveryEngine


# Paths
FRONTEND_DIR = Path(__file__).parent
STATIC_DIR = FRONTEND_DIR / "static"
TEMPLATES_DIR = FRONTEND_DIR / "templates"

# Global instances (shared with base app)
store = None
tracker = None
recovery = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan manager for the combined app."""
    global store, tracker, recovery

    db_path = os.environ.get("AGENTROLLBACK_DB", "agent_rollback.db")
    store = StateStore(db_path=db_path)
    await store.initialize()
    tracker = StateTracker(store=store)
    recovery = RecoveryEngine(store=store)

    # Update base app globals
    import agent_rollback.server as server_module
    server_module._store = store
    server_module._tracker = tracker
    server_module._recovery = recovery

    yield

    await store.close()


# Create the combined app
app = FastAPI(
    title="AgentRollback Dashboard",
    description="AI Agent State Recovery System with Web Dashboard",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Include all API routes from base app
for route in base_app.routes:
    if hasattr(route, 'path') and route.path.startswith('/api'):
        app.routes.append(route)

# Also include health endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    from datetime import datetime
    return {
        "status": "healthy",
        "version": "0.1.0",
        "timestamp": datetime.utcnow().isoformat(),
    }


# Frontend routes
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Serve the main dashboard."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_redirect():
    """Redirect to API docs."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/api/docs")


# Re-mount API documentation
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html


@app.get("/api/docs", include_in_schema=False)
async def swagger_ui():
    """Swagger UI for API."""
    return get_swagger_ui_html(
        openapi_url="/api/openapi.json",
        title="AgentRollback API Docs",
    )


@app.get("/api/openapi.json", include_in_schema=False)
async def openapi_json():
    """OpenAPI schema."""
    return app.openapi()


def run_dashboard(
    host: str = "127.0.0.1",
    port: int = 8000,
    db_path: str = "agent_rollback.db",
    reload: bool = False,
):
    """Run the dashboard server.

    Args:
        host: Host to bind to
        port: Port to bind to
        db_path: Path to SQLite database
        reload: Enable auto-reload
    """
    import uvicorn
    os.environ["AGENTROLLBACK_DB"] = db_path

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                  AgentRollback Dashboard                     ║
╠══════════════════════════════════════════════════════════════╣
║  Dashboard:  http://{host}:{port}/
║  API Docs:   http://{host}:{port}/docs
║  Database:   {db_path}
╚══════════════════════════════════════════════════════════════╝
""")

    uvicorn.run(
        "frontend.app:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    run_dashboard()
