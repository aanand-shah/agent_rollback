"""
Basic usage example for AgentRollback.

This example demonstrates:
- Starting a tracking session
- Recording actions with state snapshots
- Creating checkpoints
- Viewing session history
- Performing a rollback
"""

import asyncio
from agent_rollback.sdk import AgentRollbackClient
from agent_rollback.models import SessionStatus


async def main():
    # Create a client in local mode (no server required)
    client = AgentRollbackClient(local=True, db_path="example.db")

    async with client:
        # Start a tracking session
        session = await client.start_session(
            agent_id="example-agent",
            metadata={"task": "data processing", "version": "1.0"},
        )
        print(f"Started session: {session.id}")

        # Simulate some agent actions with state tracking
        initial_state = {"counter": 0, "items": []}

        # Action 1: Initialize
        action1 = await client.record_action(
            action_type="initialize",
            action_data={"config": "default"},
            before_state=None,
            after_state=initial_state,
            connector_type="memory",
        )
        print(f"Recorded action: {action1.action_type}")

        # Action 2: Add item
        state_after_add = {"counter": 1, "items": ["item1"]}
        action2 = await client.record_action(
            action_type="add_item",
            action_data={"item": "item1"},
            before_state=initial_state,
            after_state=state_after_add,
            connector_type="memory",
        )
        print(f"Recorded action: {action2.action_type}")

        # Create a checkpoint
        checkpoint = await client.create_checkpoint(
            state_data=state_after_add,
            connector_type="memory",
        )
        print(f"Created checkpoint: {checkpoint.id}")

        # Action 3: Add another item
        state_after_add2 = {"counter": 2, "items": ["item1", "item2"]}
        action3 = await client.record_action(
            action_type="add_item",
            action_data={"item": "item2"},
            before_state=state_after_add,
            after_state=state_after_add2,
            connector_type="memory",
        )
        print(f"Recorded action: {action3.action_type}")

        # Action 4: A mistake - let's say we want to rollback
        bad_state = {"counter": -1, "items": ["error"]}
        action4 = await client.record_action(
            action_type="process_error",
            action_data={"error": "something went wrong"},
            before_state=state_after_add2,
            after_state=bad_state,
            connector_type="memory",
        )
        print(f"Recorded action: {action4.action_type}")

        # List all actions
        print("\n--- Session Actions ---")
        actions = await client.list_actions()
        for action in actions:
            print(f"  {action.executed_at}: {action.action_type}")

        # List all snapshots
        print("\n--- Session Snapshots ---")
        snapshots = await client.list_snapshots()
        for snapshot in snapshots:
            print(f"  {snapshot.created_at}: {snapshot.snapshot_type.value} ({snapshot.connector_type})")

        # Preview rollback to checkpoint
        print("\n--- Rollback Preview ---")
        rollback_result = await client.rollback(
            target_snapshot_id=checkpoint.id,
            dry_run=True,
        )
        print(f"Would revert {rollback_result.actions_reverted} actions")

        # Perform actual rollback (uncomment to execute)
        # rollback_result = await client.rollback(
        #     target_snapshot_id=checkpoint.id,
        #     dry_run=False,
        # )
        # print(f"Rolled back {rollback_result.actions_reverted} actions")

        # End session
        await client.end_session(status=SessionStatus.COMPLETED)
        print(f"\nSession completed: {session.id}")


if __name__ == "__main__":
    asyncio.run(main())
