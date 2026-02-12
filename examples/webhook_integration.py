"""
Webhook integration example for AgentRollback.

This example demonstrates how to integrate AgentRollback with AI agents
that communicate via webhooks/HTTP endpoints, such as:
- OpenAI function calling agents
- Custom agent frameworks
- External automation tools

The pattern:
1. Start the AgentRollback server
2. Your agent sends webhooks to record actions
3. Use the API to manage sessions and perform rollbacks
"""

import asyncio
import httpx
from datetime import datetime


# Configuration
AGENT_ROLLBACK_URL = "http://localhost:8000"
AGENT_ID = "webhook-agent-demo"


async def demo_webhook_integration():
    """Demonstrate webhook-based integration with AgentRollback."""

    async with httpx.AsyncClient(base_url=AGENT_ROLLBACK_URL, timeout=30.0) as client:
        print("=== AgentRollback Webhook Integration Demo ===\n")

        # 1. Check server health
        print("1. Checking server health...")
        try:
            response = await client.get("/health")
            response.raise_for_status()
            health = response.json()
            print(f"   Server status: {health['status']}")
            print(f"   Version: {health['version']}")
        except httpx.ConnectError:
            print("   ERROR: Could not connect to AgentRollback server.")
            print("   Start the server with: python -m agent_rollback serve")
            return

        # 2. Create a session
        print("\n2. Creating tracking session...")
        response = await client.post(
            "/api/v1/sessions",
            json={
                "agent_id": AGENT_ID,
                "metadata": {
                    "source": "webhook_demo",
                    "started_at": datetime.utcnow().isoformat(),
                },
            },
        )
        response.raise_for_status()
        session_data = response.json()
        session_id = session_data["session"]["id"]
        print(f"   Session ID: {session_id}")

        # 3. Record some actions via webhooks
        print("\n3. Recording actions via webhooks...")

        # Action 1: Agent received user query
        action1_response = await client.post(
            f"/api/v1/sessions/{session_id}/actions",
            json={
                "session_id": session_id,
                "action_type": "user_query",
                "action_data": {
                    "query": "What is the weather in San Francisco?",
                    "timestamp": datetime.utcnow().isoformat(),
                },
                "before_state": {"conversation": []},
                "after_state": {
                    "conversation": [
                        {"role": "user", "content": "What is the weather in San Francisco?"}
                    ]
                },
                "connector_type": "conversation",
            },
        )
        action1 = action1_response.json()
        print(f"   Recorded: {action1['action']['action_type']}")

        # Action 2: Agent called external API
        action2_response = await client.post(
            f"/api/v1/sessions/{session_id}/actions",
            json={
                "session_id": session_id,
                "action_type": "api_call",
                "action_data": {
                    "api": "weather_api",
                    "endpoint": "/current",
                    "params": {"city": "San Francisco"},
                    "response": {"temp": 65, "condition": "sunny"},
                },
                "before_state": {"api_calls": 0},
                "after_state": {"api_calls": 1, "last_api": "weather_api"},
                "connector_type": "api",
            },
        )
        action2 = action2_response.json()
        print(f"   Recorded: {action2['action']['action_type']}")

        # 4. Create a checkpoint
        print("\n4. Creating checkpoint...")
        checkpoint_response = await client.post(
            f"/api/v1/sessions/{session_id}/checkpoint",
            json={
                "connector_type": "conversation",
                "state_data": {
                    "conversation": [
                        {"role": "user", "content": "What is the weather in San Francisco?"},
                        {"role": "assistant", "content": "The weather in San Francisco is 65F and sunny."},
                    ],
                    "api_calls": 1,
                },
            },
        )
        checkpoint = checkpoint_response.json()
        checkpoint_id = checkpoint["snapshot"]["id"]
        print(f"   Checkpoint ID: {checkpoint_id}")

        # Action 3: Agent generated response
        action3_response = await client.post(
            f"/api/v1/sessions/{session_id}/actions",
            json={
                "session_id": session_id,
                "action_type": "generate_response",
                "action_data": {
                    "response": "The weather in San Francisco is 65F and sunny.",
                },
                "connector_type": "conversation",
            },
        )
        action3 = action3_response.json()
        print(f"   Recorded: {action3['action']['action_type']}")

        # Action 4: Simulated error
        action4_response = await client.post(
            f"/api/v1/sessions/{session_id}/actions",
            json={
                "session_id": session_id,
                "action_type": "error_action",
                "action_data": {
                    "error": "Something went wrong",
                    "recoverable": True,
                },
                "before_state": {"status": "ok"},
                "after_state": {"status": "error"},
                "connector_type": "system",
            },
        )
        action4 = action4_response.json()
        print(f"   Recorded: {action4['action']['action_type']}")

        # 5. Get session timeline
        print("\n5. Fetching session timeline...")
        timeline_response = await client.get(f"/api/v1/sessions/{session_id}/timeline")
        timeline = timeline_response.json()
        print(f"   Total actions: {timeline['total_actions']}")
        print(f"   Total snapshots: {timeline['total_snapshots']}")
        print("   Timeline:")
        for entry in timeline["entries"]:
            if entry["event_type"] == "action":
                print(f"     - Action: {entry['action']['action_type']}")
            else:
                print(f"     - {entry['event_type'].title()}")

        # 6. List recovery points
        print("\n6. Available recovery points...")
        recovery_response = await client.get(
            f"/api/v1/sessions/{session_id}/recovery-points"
        )
        recovery_points = recovery_response.json()
        for point in recovery_points:
            print(f"   - {point['type']} at {point['timestamp']} ({point['snapshot_id'][:8]}...)")

        # 7. Preview rollback
        print("\n7. Previewing rollback to checkpoint...")
        preview_response = await client.get(
            "/api/v1/rollback/preview",
            params={
                "session_id": session_id,
                "target_snapshot_id": checkpoint_id,
            },
        )
        preview = preview_response.json()
        print(f"   Actions to revert: {preview['actions_to_revert']}")
        print(f"   Action types: {preview['action_types']}")

        # 8. Diff snapshots
        print("\n8. Comparing snapshots...")
        snapshots_response = await client.get(
            f"/api/v1/sessions/{session_id}/snapshots"
        )
        snapshots = snapshots_response.json()["snapshots"]

        if len(snapshots) >= 2:
            diff_response = await client.get(
                "/api/v1/diff",
                params={
                    "snapshot_a_id": snapshots[-1]["id"],
                    "snapshot_b_id": snapshots[0]["id"],
                },
            )
            diff_result = diff_response.json()
            print(f"   Changes: {diff_result['summary']}")

        # 9. Execute rollback (dry run)
        print("\n9. Executing rollback (dry run)...")
        rollback_response = await client.post(
            "/api/v1/rollback",
            json={
                "session_id": session_id,
                "target_snapshot_id": checkpoint_id,
                "dry_run": True,
            },
        )
        rollback_result = rollback_response.json()
        print(f"   Success: {rollback_result['success']}")
        print(f"   Would revert: {rollback_result['actions_reverted']} actions")

        # 10. End session
        print("\n10. Ending session...")
        end_response = await client.delete(
            f"/api/v1/sessions/{session_id}",
            params={"status": "completed"},
        )
        print(f"   Session ended: {end_response.json()['session']['status']}")

        print("\n=== Demo Complete ===")
        print(f"\nSession ID: {session_id}")
        print("View full history with: agentrollback log " + session_id[:8])


def main():
    """Run the webhook integration demo."""
    print("AgentRollback Webhook Integration Demo")
    print("=" * 40)
    print("\nThis demo requires the AgentRollback server to be running.")
    print("Start it with: python -m agent_rollback serve\n")

    asyncio.run(demo_webhook_integration())


if __name__ == "__main__":
    main()
