#!/usr/bin/env python3
"""
Launcher script for AgentRollback Dashboard.

Usage:
    python run_dashboard.py [--host HOST] [--port PORT] [--reload]
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from frontend.app import run_dashboard

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run AgentRollback Dashboard")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--db", default="agent_rollback.db", help="Database path")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")

    args = parser.parse_args()
    run_dashboard(host=args.host, port=args.port, db_path=args.db, reload=args.reload)
