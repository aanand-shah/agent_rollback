"""
JSON serialization helpers for state data.
"""

import json
from datetime import datetime, date
from typing import Any
from pathlib import Path
import base64


class StateEncoder(json.JSONEncoder):
    """Custom JSON encoder for state data.

    Handles common Python types that aren't JSON-serializable by default.
    """

    def default(self, obj: Any) -> Any:
        if isinstance(obj, datetime):
            return {"__type__": "datetime", "value": obj.isoformat()}
        elif isinstance(obj, date):
            return {"__type__": "date", "value": obj.isoformat()}
        elif isinstance(obj, bytes):
            return {"__type__": "bytes", "value": base64.b64encode(obj).decode("ascii")}
        elif isinstance(obj, Path):
            return {"__type__": "path", "value": str(obj)}
        elif isinstance(obj, set):
            return {"__type__": "set", "value": list(obj)}
        elif isinstance(obj, frozenset):
            return {"__type__": "frozenset", "value": list(obj)}
        elif hasattr(obj, "__dict__"):
            return {"__type__": "object", "class": type(obj).__name__, "value": obj.__dict__}
        return super().default(obj)


def state_decoder_hook(obj: dict) -> Any:
    """Object hook for decoding custom types from JSON.

    Args:
        obj: Dictionary that might contain encoded custom type

    Returns:
        Decoded object or original dictionary
    """
    if "__type__" not in obj:
        return obj

    type_name = obj["__type__"]
    value = obj.get("value")

    if type_name == "datetime":
        return datetime.fromisoformat(value)
    elif type_name == "date":
        return date.fromisoformat(value)
    elif type_name == "bytes":
        return base64.b64decode(value)
    elif type_name == "path":
        return Path(value)
    elif type_name == "set":
        return set(value)
    elif type_name == "frozenset":
        return frozenset(value)
    elif type_name == "object":
        # Return as dict for object types
        return value

    return obj


def serialize_state(state: Any) -> str:
    """Serialize state data to JSON string.

    Args:
        state: State data to serialize

    Returns:
        JSON string
    """
    return json.dumps(state, cls=StateEncoder, indent=2)


def deserialize_state(json_str: str) -> Any:
    """Deserialize JSON string to state data.

    Args:
        json_str: JSON string to deserialize

    Returns:
        Deserialized state data
    """
    return json.loads(json_str, object_hook=state_decoder_hook)


def safe_serialize(obj: Any) -> Any:
    """Safely convert an object to a JSON-serializable form.

    Args:
        obj: Object to convert

    Returns:
        JSON-serializable version of object
    """
    if obj is None:
        return None
    elif isinstance(obj, (str, int, float, bool)):
        return obj
    elif isinstance(obj, (datetime, date)):
        return obj.isoformat()
    elif isinstance(obj, bytes):
        return base64.b64encode(obj).decode("ascii")
    elif isinstance(obj, Path):
        return str(obj)
    elif isinstance(obj, (set, frozenset)):
        return [safe_serialize(item) for item in obj]
    elif isinstance(obj, dict):
        return {str(k): safe_serialize(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [safe_serialize(item) for item in obj]
    elif hasattr(obj, "__dict__"):
        return {
            "__class__": type(obj).__name__,
            **{k: safe_serialize(v) for k, v in obj.__dict__.items()},
        }
    else:
        return str(obj)


def deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dictionaries.

    Args:
        base: Base dictionary
        override: Dictionary with values to overlay

    Returns:
        Merged dictionary
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def flatten_dict(
    d: dict,
    parent_key: str = "",
    separator: str = ".",
) -> dict[str, Any]:
    """Flatten a nested dictionary to a single level.

    Args:
        d: Dictionary to flatten
        parent_key: Prefix for keys (used in recursion)
        separator: Separator between nested keys

    Returns:
        Flattened dictionary
    """
    items = []
    for key, value in d.items():
        new_key = f"{parent_key}{separator}{key}" if parent_key else key
        if isinstance(value, dict):
            items.extend(flatten_dict(value, new_key, separator).items())
        else:
            items.append((new_key, value))
    return dict(items)


def unflatten_dict(d: dict[str, Any], separator: str = ".") -> dict:
    """Unflatten a dictionary with dotted keys to nested structure.

    Args:
        d: Flattened dictionary
        separator: Separator between key parts

    Returns:
        Nested dictionary
    """
    result = {}
    for key, value in d.items():
        parts = key.split(separator)
        current = result
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value
    return result
