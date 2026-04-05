"""Shared utility functions."""

import json


def rows_to_dicts(result):
    """Convert Kuzu result to list of dicts using native iteration."""
    columns = result.get_column_names()
    rows = []
    while result.has_next():
        values = result.get_next()
        rows.append(dict(zip(columns, values)))
    return rows


def parse_props(raw):
    """Parse properties JSON string into a dict, handling edge cases.

    Handles double-encoded JSON (Kuzu may store strings with extra escaping).
    """
    if not raw or raw in ('{}', ''):
        return None
    if not isinstance(raw, str):
        return raw
    try:
        parsed = json.loads(raw)
        # Handle double-encoded: json.loads yields str instead of dict
        if isinstance(parsed, str):
            parsed = json.loads(parsed)
        return parsed if isinstance(parsed, dict) else raw
    except (json.JSONDecodeError, TypeError):
        return raw
