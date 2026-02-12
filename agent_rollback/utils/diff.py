"""
State diffing utilities for comparing snapshots.
"""

from typing import Any

from agent_rollback.models import DiffChange, DiffResult


def compute_diff(
    state_a: dict[str, Any],
    state_b: dict[str, Any],
    path_prefix: str = "",
) -> list[DiffChange]:
    """Compute the differences between two state dictionaries.

    Args:
        state_a: The first state (before)
        state_b: The second state (after)
        path_prefix: Prefix for JSON paths (used in recursion)

    Returns:
        List of DiffChange objects describing all differences
    """
    changes = []

    # Get all keys from both states
    all_keys = set(state_a.keys()) | set(state_b.keys())

    for key in sorted(all_keys):
        current_path = f"{path_prefix}.{key}" if path_prefix else key
        in_a = key in state_a
        in_b = key in state_b

        if in_a and not in_b:
            # Key was removed
            changes.append(
                DiffChange(
                    path=current_path,
                    operation="remove",
                    old_value=state_a[key],
                    new_value=None,
                )
            )
        elif not in_a and in_b:
            # Key was added
            changes.append(
                DiffChange(
                    path=current_path,
                    operation="add",
                    old_value=None,
                    new_value=state_b[key],
                )
            )
        else:
            # Key exists in both
            val_a = state_a[key]
            val_b = state_b[key]

            if isinstance(val_a, dict) and isinstance(val_b, dict):
                # Recurse into nested dicts
                changes.extend(compute_diff(val_a, val_b, current_path))
            elif isinstance(val_a, list) and isinstance(val_b, list):
                # Compare lists
                list_changes = _compare_lists(val_a, val_b, current_path)
                changes.extend(list_changes)
            elif val_a != val_b:
                # Value was modified
                changes.append(
                    DiffChange(
                        path=current_path,
                        operation="modify",
                        old_value=val_a,
                        new_value=val_b,
                    )
                )

    return changes


def _compare_lists(
    list_a: list,
    list_b: list,
    path: str,
) -> list[DiffChange]:
    """Compare two lists and return changes.

    Args:
        list_a: First list
        list_b: Second list
        path: JSON path to the list

    Returns:
        List of changes
    """
    changes = []

    # Simple length comparison
    if len(list_a) != len(list_b):
        changes.append(
            DiffChange(
                path=f"{path}.__length__",
                operation="modify",
                old_value=len(list_a),
                new_value=len(list_b),
            )
        )

    # Compare elements
    max_len = max(len(list_a), len(list_b))
    for i in range(max_len):
        item_path = f"{path}[{i}]"

        if i >= len(list_a):
            # Item was added
            changes.append(
                DiffChange(
                    path=item_path,
                    operation="add",
                    old_value=None,
                    new_value=list_b[i],
                )
            )
        elif i >= len(list_b):
            # Item was removed
            changes.append(
                DiffChange(
                    path=item_path,
                    operation="remove",
                    old_value=list_a[i],
                    new_value=None,
                )
            )
        else:
            val_a = list_a[i]
            val_b = list_b[i]

            if isinstance(val_a, dict) and isinstance(val_b, dict):
                changes.extend(compute_diff(val_a, val_b, item_path))
            elif isinstance(val_a, list) and isinstance(val_b, list):
                changes.extend(_compare_lists(val_a, val_b, item_path))
            elif val_a != val_b:
                changes.append(
                    DiffChange(
                        path=item_path,
                        operation="modify",
                        old_value=val_a,
                        new_value=val_b,
                    )
                )

    return changes


def format_diff(changes: list[DiffChange], colorize: bool = False) -> str:
    """Format a list of changes as a human-readable string.

    Args:
        changes: List of changes to format
        colorize: Whether to add ANSI color codes

    Returns:
        Formatted string representation
    """
    if not changes:
        return "No changes"

    lines = []
    for change in changes:
        if change.operation == "add":
            prefix = "+" if not colorize else "\033[32m+"
            suffix = "" if not colorize else "\033[0m"
            lines.append(f"{prefix} {change.path}: {change.new_value}{suffix}")
        elif change.operation == "remove":
            prefix = "-" if not colorize else "\033[31m-"
            suffix = "" if not colorize else "\033[0m"
            lines.append(f"{prefix} {change.path}: {change.old_value}{suffix}")
        elif change.operation == "modify":
            prefix = "~" if not colorize else "\033[33m~"
            suffix = "" if not colorize else "\033[0m"
            lines.append(
                f"{prefix} {change.path}: {change.old_value} -> {change.new_value}{suffix}"
            )

    return "\n".join(lines)


def summarize_diff(changes: list[DiffChange]) -> str:
    """Create a summary of changes.

    Args:
        changes: List of changes

    Returns:
        Summary string
    """
    if not changes:
        return "No changes detected"

    adds = sum(1 for c in changes if c.operation == "add")
    removes = sum(1 for c in changes if c.operation == "remove")
    modifies = sum(1 for c in changes if c.operation == "modify")

    parts = []
    if adds:
        parts.append(f"{adds} addition{'s' if adds != 1 else ''}")
    if removes:
        parts.append(f"{removes} removal{'s' if removes != 1 else ''}")
    if modifies:
        parts.append(f"{modifies} modification{'s' if modifies != 1 else ''}")

    return ", ".join(parts)


def create_diff_result(
    snapshot_a_id: str,
    snapshot_b_id: str,
    state_a: dict[str, Any],
    state_b: dict[str, Any],
) -> DiffResult:
    """Create a complete diff result comparing two snapshots.

    Args:
        snapshot_a_id: ID of first snapshot
        snapshot_b_id: ID of second snapshot
        state_a: State data from first snapshot
        state_b: State data from second snapshot

    Returns:
        DiffResult with changes and summary
    """
    changes = compute_diff(state_a, state_b)
    summary = summarize_diff(changes)

    return DiffResult(
        snapshot_a_id=snapshot_a_id,
        snapshot_b_id=snapshot_b_id,
        changes=changes,
        summary=summary,
    )
