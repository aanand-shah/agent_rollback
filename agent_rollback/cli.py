"""
Command-line interface for AgentRollback.

Provides commands for managing sessions, viewing history, and performing
rollback operations.
"""

import asyncio
import json
import sys
from datetime import datetime
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.tree import Tree

from agent_rollback.store import StateStore
from agent_rollback.tracker import StateTracker
from agent_rollback.recovery import RecoveryEngine
from agent_rollback.models import SessionStatus, SnapshotType, RollbackRequest, ReplayRequest
from agent_rollback.utils.diff import format_diff


console = Console()


def run_async(coro):
    """Run an async coroutine in the event loop."""
    return asyncio.get_event_loop().run_until_complete(coro)


@click.group()
@click.option("--db", default="agent_rollback.db", help="Database path")
@click.pass_context
def cli(ctx, db):
    """AgentRollback - AI Agent State Recovery System.

    Git for AI Agents: Track, rollback, and replay agent actions.
    """
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = db


@cli.command()
@click.pass_context
def status(ctx):
    """Show active sessions and system status."""
    db_path = ctx.obj["db_path"]

    async def _status():
        store = StateStore(db_path=db_path)
        await store.initialize()

        # Get active sessions
        active = await store.list_sessions(status=SessionStatus.ACTIVE)
        total = await store.list_sessions(limit=1000)

        console.print(Panel.fit(
            f"[bold blue]AgentRollback Status[/bold blue]\n\n"
            f"Database: {db_path}\n"
            f"Active Sessions: [green]{len(active)}[/green]\n"
            f"Total Sessions: {len(total)}",
            title="System Status"
        ))

        if active:
            table = Table(title="Active Sessions")
            table.add_column("Session ID", style="cyan")
            table.add_column("Agent ID", style="green")
            table.add_column("Started", style="yellow")
            table.add_column("Actions", style="magenta")

            for session in active:
                actions = await store.list_actions(session_id=session.id)
                table.add_row(
                    session.id[:8] + "...",
                    session.agent_id,
                    session.started_at.strftime("%Y-%m-%d %H:%M"),
                    str(len(actions)),
                )

            console.print(table)

    run_async(_status())


@cli.command()
@click.argument("session_id")
@click.option("--limit", default=50, help="Maximum actions to show")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.pass_context
def log(ctx, session_id, limit, json_output):
    """Show action history for a session."""
    db_path = ctx.obj["db_path"]

    async def _log():
        store = StateStore(db_path=db_path)
        await store.initialize()

        # Find session (support partial IDs)
        sessions = await store.list_sessions()
        session = None
        for s in sessions:
            if s.id.startswith(session_id):
                session = s
                break

        if not session:
            console.print(f"[red]Session not found: {session_id}[/red]")
            return

        actions = await store.list_actions(session_id=session.id, limit=limit)

        if json_output:
            output = {
                "session": session.model_dump(mode="json"),
                "actions": [a.model_dump(mode="json") for a in actions],
            }
            console.print(json.dumps(output, indent=2, default=str))
            return

        # Display session info
        console.print(Panel.fit(
            f"[bold]Session:[/bold] {session.id}\n"
            f"[bold]Agent:[/bold] {session.agent_id}\n"
            f"[bold]Status:[/bold] {session.status.value}\n"
            f"[bold]Started:[/bold] {session.started_at}\n"
            f"[bold]Ended:[/bold] {session.ended_at or 'Active'}",
            title="Session Details"
        ))

        # Display action timeline
        tree = Tree(f"[bold]Action Timeline ({len(actions)} actions)[/bold]")
        for action in actions:
            action_node = tree.add(
                f"[cyan]{action.executed_at.strftime('%H:%M:%S')}[/cyan] "
                f"[green]{action.action_type}[/green] "
                f"[dim]({action.status.value})[/dim]"
            )
            if action.action_data:
                action_node.add(f"[dim]{json.dumps(action.action_data, default=str)[:100]}[/dim]")
            if action.before_snapshot_id:
                action_node.add(f"[yellow]Before:[/yellow] {action.before_snapshot_id[:8]}...")
            if action.after_snapshot_id:
                action_node.add(f"[yellow]After:[/yellow] {action.after_snapshot_id[:8]}...")

        console.print(tree)

    run_async(_log())


@cli.command()
@click.argument("session_id")
@click.argument("snapshot_id")
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--force", is_flag=True, help="Skip confirmation")
@click.pass_context
def rollback(ctx, session_id, snapshot_id, dry_run, force):
    """Rollback a session to a specific snapshot."""
    db_path = ctx.obj["db_path"]

    async def _rollback():
        store = StateStore(db_path=db_path)
        await store.initialize()
        recovery = RecoveryEngine(store=store)

        # Find session
        sessions = await store.list_sessions()
        session = None
        for s in sessions:
            if s.id.startswith(session_id):
                session = s
                break

        if not session:
            console.print(f"[red]Session not found: {session_id}[/red]")
            return

        # Find snapshot
        snapshots = await store.list_snapshots(session_id=session.id)
        snapshot = None
        for s in snapshots:
            if s.id.startswith(snapshot_id):
                snapshot = s
                break

        if not snapshot:
            console.print(f"[red]Snapshot not found: {snapshot_id}[/red]")
            return

        # Preview
        preview = await recovery.get_rollback_preview(session.id, snapshot.id)
        console.print(Panel.fit(
            f"[bold]Target Snapshot:[/bold] {snapshot.id}\n"
            f"[bold]Snapshot Time:[/bold] {snapshot.created_at}\n"
            f"[bold]Actions to Revert:[/bold] {preview['actions_to_revert']}\n"
            f"[bold]Action Types:[/bold] {', '.join(preview['action_types'])}",
            title="Rollback Preview"
        ))

        if dry_run:
            console.print("[yellow]Dry run - no changes made[/yellow]")
            return

        if not force:
            if not click.confirm("Proceed with rollback?"):
                console.print("[yellow]Rollback cancelled[/yellow]")
                return

        # Execute rollback
        request = RollbackRequest(
            session_id=session.id,
            target_snapshot_id=snapshot.id,
            dry_run=False,
        )
        result = await recovery.rollback(request)

        if result.success:
            console.print(f"[green]Rollback successful![/green]")
            console.print(f"Actions reverted: {result.actions_reverted}")
        else:
            console.print(f"[red]Rollback failed[/red]")
            for error in result.errors:
                console.print(f"  [red]{error}[/red]")

    run_async(_rollback())


@cli.command()
@click.argument("snapshot_a")
@click.argument("snapshot_b")
@click.option("--color/--no-color", default=True, help="Colorize output")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.pass_context
def diff(ctx, snapshot_a, snapshot_b, color, json_output):
    """Show differences between two snapshots."""
    db_path = ctx.obj["db_path"]

    async def _diff():
        store = StateStore(db_path=db_path)
        await store.initialize()
        recovery = RecoveryEngine(store=store)

        # Find snapshots by partial ID
        all_snapshots = await store.list_snapshots(limit=10000)

        snap_a = None
        snap_b = None
        for s in all_snapshots:
            if s.id.startswith(snapshot_a):
                snap_a = s
            if s.id.startswith(snapshot_b):
                snap_b = s

        if not snap_a:
            console.print(f"[red]Snapshot not found: {snapshot_a}[/red]")
            return
        if not snap_b:
            console.print(f"[red]Snapshot not found: {snapshot_b}[/red]")
            return

        result = await recovery.diff(snap_a.id, snap_b.id)

        if json_output:
            console.print(json.dumps(result.model_dump(mode="json"), indent=2, default=str))
            return

        console.print(Panel.fit(
            f"[bold]Snapshot A:[/bold] {snap_a.id[:8]}... ({snap_a.created_at})\n"
            f"[bold]Snapshot B:[/bold] {snap_b.id[:8]}... ({snap_b.created_at})\n"
            f"[bold]Summary:[/bold] {result.summary}",
            title="Diff Result"
        ))

        if result.changes:
            diff_text = format_diff(result.changes, colorize=color)
            console.print(Syntax(diff_text, "diff", theme="monokai"))
        else:
            console.print("[dim]No changes detected[/dim]")

    run_async(_diff())


@cli.command()
@click.argument("session_id")
@click.option("--output", "-o", help="Output file path")
@click.option("--format", "fmt", type=click.Choice(["json", "yaml"]), default="json")
@click.pass_context
def export(ctx, session_id, output, fmt):
    """Export session data."""
    db_path = ctx.obj["db_path"]

    async def _export():
        store = StateStore(db_path=db_path)
        await store.initialize()

        # Find session
        sessions = await store.list_sessions()
        session = None
        for s in sessions:
            if s.id.startswith(session_id):
                session = s
                break

        if not session:
            console.print(f"[red]Session not found: {session_id}[/red]")
            return

        # Gather all data
        actions = await store.list_actions(session_id=session.id, limit=10000)
        snapshots = await store.list_snapshots(session_id=session.id, limit=10000)

        data = {
            "exported_at": datetime.utcnow().isoformat(),
            "session": session.model_dump(mode="json"),
            "actions": [a.model_dump(mode="json") for a in actions],
            "snapshots": [s.model_dump(mode="json") for s in snapshots],
        }

        if fmt == "json":
            export_str = json.dumps(data, indent=2, default=str)
        else:
            # YAML export
            try:
                import yaml
                export_str = yaml.dump(data, default_flow_style=False)
            except ImportError:
                console.print("[red]PyYAML not installed. Use JSON format.[/red]")
                return

        if output:
            with open(output, "w") as f:
                f.write(export_str)
            console.print(f"[green]Exported to {output}[/green]")
        else:
            console.print(export_str)

    run_async(_export())


@cli.command()
@click.option("--all", "all_sessions", is_flag=True, help="List all sessions")
@click.option("--status", "filter_status", type=click.Choice(["active", "completed", "failed", "rolled_back"]))
@click.option("--agent", "agent_id", help="Filter by agent ID")
@click.option("--limit", default=20, help="Maximum sessions to show")
@click.pass_context
def sessions(ctx, all_sessions, filter_status, agent_id, limit):
    """List tracking sessions."""
    db_path = ctx.obj["db_path"]

    async def _sessions():
        store = StateStore(db_path=db_path)
        await store.initialize()

        status = None
        if filter_status:
            status = SessionStatus(filter_status)
        elif not all_sessions:
            status = SessionStatus.ACTIVE

        sessions_list = await store.list_sessions(
            status=status,
            agent_id=agent_id,
            limit=limit,
        )

        if not sessions_list:
            console.print("[dim]No sessions found[/dim]")
            return

        table = Table(title=f"Sessions ({len(sessions_list)} shown)")
        table.add_column("ID", style="cyan")
        table.add_column("Agent", style="green")
        table.add_column("Status", style="yellow")
        table.add_column("Started", style="blue")
        table.add_column("Duration", style="magenta")

        for session in sessions_list:
            duration = ""
            if session.ended_at:
                delta = session.ended_at - session.started_at
                duration = str(delta).split(".")[0]
            elif session.status == SessionStatus.ACTIVE:
                delta = datetime.utcnow() - session.started_at
                duration = f"{str(delta).split('.')[0]} (ongoing)"

            status_style = {
                SessionStatus.ACTIVE: "[green]active[/green]",
                SessionStatus.COMPLETED: "[blue]completed[/blue]",
                SessionStatus.FAILED: "[red]failed[/red]",
                SessionStatus.ROLLED_BACK: "[yellow]rolled_back[/yellow]",
            }.get(session.status, session.status.value)

            table.add_row(
                session.id[:12] + "...",
                session.agent_id,
                status_style,
                session.started_at.strftime("%Y-%m-%d %H:%M"),
                duration,
            )

        console.print(table)

    run_async(_sessions())


@cli.command()
@click.argument("session_id")
@click.pass_context
def snapshots(ctx, session_id):
    """List snapshots for a session."""
    db_path = ctx.obj["db_path"]

    async def _snapshots():
        store = StateStore(db_path=db_path)
        await store.initialize()

        # Find session
        sessions = await store.list_sessions()
        session = None
        for s in sessions:
            if s.id.startswith(session_id):
                session = s
                break

        if not session:
            console.print(f"[red]Session not found: {session_id}[/red]")
            return

        snapshots_list = await store.list_snapshots(session_id=session.id, limit=100)

        if not snapshots_list:
            console.print("[dim]No snapshots found[/dim]")
            return

        table = Table(title=f"Snapshots for {session.id[:12]}...")
        table.add_column("ID", style="cyan")
        table.add_column("Type", style="green")
        table.add_column("Connector", style="yellow")
        table.add_column("Created", style="blue")
        table.add_column("Data Size", style="magenta")

        for snapshot in snapshots_list:
            type_style = {
                SnapshotType.BEFORE: "[yellow]before[/yellow]",
                SnapshotType.AFTER: "[green]after[/green]",
                SnapshotType.CHECKPOINT: "[blue]checkpoint[/blue]",
            }.get(snapshot.snapshot_type, snapshot.snapshot_type.value)

            data_size = len(json.dumps(snapshot.state_data))

            table.add_row(
                snapshot.id[:12] + "...",
                type_style,
                f"{snapshot.connector_type}:{snapshot.connector_id or '*'}",
                snapshot.created_at.strftime("%H:%M:%S"),
                f"{data_size} bytes",
            )

        console.print(table)

    run_async(_snapshots())


@cli.command()
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=8000, help="Port to bind to")
@click.option("--reload", is_flag=True, help="Enable auto-reload")
@click.pass_context
def serve(ctx, host, port, reload):
    """Start the REST API server."""
    db_path = ctx.obj["db_path"]

    from agent_rollback.server import run_server
    console.print(f"[green]Starting AgentRollback server on {host}:{port}[/green]")
    console.print(f"[dim]Database: {db_path}[/dim]")
    console.print(f"[dim]API docs: http://{host}:{port}/docs[/dim]")
    run_server(host=host, port=port, db_path=db_path, reload=reload)


def main():
    """Main entry point for CLI."""
    cli(obj={})


if __name__ == "__main__":
    main()
