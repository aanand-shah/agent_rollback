"""
LangChain integration example for AgentRollback.

This example demonstrates how to integrate AgentRollback with LangChain
agents to track tool calls and enable rollback of agent operations.

Note: Requires langchain to be installed (pip install langchain)
"""

import asyncio
from typing import Any
from functools import wraps

from agent_rollback.sdk import AgentRollbackClient, TrackedAgent
from agent_rollback.models import SessionStatus

# Simulated LangChain-like structures for demonstration
# In real usage, import from langchain


class SimulatedTool:
    """Simulated LangChain tool for demonstration."""

    def __init__(self, name: str, func):
        self.name = name
        self._func = func

    def run(self, *args, **kwargs):
        return self._func(*args, **kwargs)


class TrackedLangChainAgent(TrackedAgent):
    """A LangChain agent wrapper with automatic action tracking.

    This class wraps tool executions and agent steps to automatically
    record them for later rollback.
    """

    def __init__(
        self,
        agent_id: str,
        tools: list[SimulatedTool] = None,
        **kwargs,
    ):
        super().__init__(agent_id, **kwargs)
        self.tools = tools or []
        self._tool_states: dict[str, Any] = {}

    def wrap_tool(self, tool: SimulatedTool) -> SimulatedTool:
        """Wrap a tool to track its execution.

        Args:
            tool: The tool to wrap

        Returns:
            Wrapped tool with tracking
        """
        original_run = tool.run

        @wraps(original_run)
        async def tracked_run(*args, **kwargs):
            # Capture state before tool execution
            before_state = self._capture_tool_state(tool.name)

            try:
                # Execute the tool
                result = original_run(*args, **kwargs)

                # Capture state after tool execution
                after_state = self._capture_tool_state(tool.name)
                after_state["result"] = str(result)

                # Record the action
                await self.record_action(
                    action_type=f"tool:{tool.name}",
                    action_data={
                        "args": [str(a) for a in args],
                        "kwargs": {k: str(v) for k, v in kwargs.items()},
                        "result": str(result),
                    },
                    before_state=before_state,
                    after_state=after_state,
                )

                return result
            except Exception as e:
                # Record failed action
                await self.record_action(
                    action_type=f"tool:{tool.name}",
                    action_data={
                        "args": [str(a) for a in args],
                        "kwargs": {k: str(v) for k, v in kwargs.items()},
                        "error": str(e),
                    },
                    before_state=before_state,
                    after_state={"error": str(e)},
                )
                raise

        # Return async wrapper
        async def async_wrapper(*args, **kwargs):
            return await tracked_run(*args, **kwargs)

        tool.run = lambda *args, **kwargs: asyncio.get_event_loop().run_until_complete(
            async_wrapper(*args, **kwargs)
        )
        return tool

    def _capture_tool_state(self, tool_name: str) -> dict[str, Any]:
        """Capture the current state relevant to a tool."""
        return {
            "tool_name": tool_name,
            "tool_states": dict(self._tool_states),
        }

    def set_tool_state(self, key: str, value: Any) -> None:
        """Set a tool-related state value."""
        self._tool_states[key] = value

    def get_tool_state(self, key: str, default: Any = None) -> Any:
        """Get a tool-related state value."""
        return self._tool_states.get(key, default)


# Example tools

def calculator_tool(expression: str) -> str:
    """A simple calculator tool."""
    try:
        result = eval(expression)  # Note: unsafe in production
        return str(result)
    except Exception as e:
        return f"Error: {e}"


def search_tool(query: str) -> str:
    """A simulated search tool."""
    # In real usage, this would call an actual search API
    return f"Search results for: {query}"


def write_file_tool(filename: str, content: str) -> str:
    """A simulated file writing tool."""
    # In real usage, this would write to filesystem
    # Here we just track the operation
    return f"Wrote {len(content)} bytes to {filename}"


async def main():
    # Create tools
    tools = [
        SimulatedTool("calculator", calculator_tool),
        SimulatedTool("search", search_tool),
        SimulatedTool("write_file", write_file_tool),
    ]

    # Create tracked agent
    agent = TrackedLangChainAgent(
        agent_id="langchain-demo-agent",
        tools=tools,
        local=True,
        db_path="langchain_example.db",
    )

    # Wrap tools for tracking
    wrapped_tools = [agent.wrap_tool(tool) for tool in tools]

    async with agent:
        print("Starting LangChain agent with rollback support...")

        # Simulate agent operations
        print("\n1. Running calculator...")
        calc_result = wrapped_tools[0].run("2 + 2 * 10")
        print(f"   Result: {calc_result}")

        print("\n2. Running search...")
        agent.set_tool_state("last_search_query", "AI agents")
        search_result = wrapped_tools[1].run("AI agents")
        print(f"   Result: {search_result}")

        # Create checkpoint after successful operations
        await agent.checkpoint(state_data={
            "completed_steps": 2,
            "tool_states": dict(agent._tool_states),
        })
        print("\n   [Checkpoint created]")

        print("\n3. Running file write...")
        write_result = wrapped_tools[2].run("output.txt", "Hello, World!")
        print(f"   Result: {write_result}")

        print("\n4. Running another calculation...")
        calc_result2 = wrapped_tools[0].run("100 / 5")
        print(f"   Result: {calc_result2}")

        # List recorded actions
        print("\n--- Recorded Actions ---")
        actions = await agent.client.list_actions()
        for action in actions:
            print(f"  {action.action_type}: {action.action_data}")

        # Show rollback options
        print("\n--- Available Recovery Points ---")
        snapshots = await agent.client.list_snapshots()
        for i, snap in enumerate(snapshots):
            print(f"  {i+1}. {snap.snapshot_type.value} at {snap.created_at}")

        print("\nAgent session completed with rollback support enabled.")
        print("Use 'agentrollback log <session_id>' to view the full history.")


if __name__ == "__main__":
    asyncio.run(main())
