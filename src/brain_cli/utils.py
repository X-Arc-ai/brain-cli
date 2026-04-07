"""Shared utility functions."""

import json
from datetime import datetime, timezone


def compute_staleness_for_node(updated_at, verified_at):
    """Compute (level, days) for a node given its timestamps.

    Single source of truth used by signals.compute_staleness,
    reader.query_stale, and exporter._staleness_level.

    Levels: 'ok' | 'info' (>= STALENESS_HIGH) | 'warning' (>= STALENESS_MEDIUM)
            | 'critical' (>= STALENESS_LOW) | 'unknown' (no timestamps).
    """
    # Local import avoids a circular dependency: config does not import utils,
    # but other modules that do import config also import utils.
    from .config import STALENESS_HIGH, STALENESS_MEDIUM, STALENESS_LOW

    now = datetime.now(timezone.utc)
    last_touch = verified_at if (verified_at and updated_at and verified_at > updated_at) else updated_at
    if last_touch is None:
        return "unknown", None
    if isinstance(last_touch, str):
        last_touch = datetime.fromisoformat(last_touch)
    if last_touch.tzinfo is None:
        last_touch = last_touch.replace(tzinfo=timezone.utc)
    days = (now - last_touch).days
    if days >= STALENESS_LOW:
        return "critical", days
    if days >= STALENESS_MEDIUM:
        return "warning", days
    if days >= STALENESS_HIGH:
        return "info", days
    return "ok", days


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
