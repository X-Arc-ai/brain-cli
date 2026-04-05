"""Tests for brain_cli.signals -- staleness, velocity, completion signals."""

from datetime import datetime, timezone, timedelta

import pytest

from brain_cli.writer import create_node, create_edge, _ts_param
from brain_cli.signals import (
    compute_all_signals,
    compute_staleness,
    compute_velocity_zero,
    compute_recently_completed,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _past_ts(days):
    """Return a timestamp string N days in the past."""
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return _ts_param(dt)


def _make_stale_node(conn, node_id, node_type="goal", days_old=20):
    """Create a node with old updated_at to trigger staleness."""
    old = _past_ts(days_old)
    conn.execute(
        """
        MERGE (n:Node {id: $id})
        ON CREATE SET
            n.type = $type,
            n.title = $id,
            n.status = 'active',
            n.created_at = timestamp($ts),
            n.updated_at = timestamp($ts),
            n.status_since = timestamp($ts),
            n.content = NULL,
            n.file_path = NULL,
            n.properties = NULL,
            n.content_embedding = NULL
        ON MATCH SET
            n.updated_at = timestamp($ts),
            n.status_since = timestamp($ts)
        """,
        parameters={"id": node_id, "type": node_type, "ts": old},
    )


def _make_completed_node(conn, node_id, days_ago=1):
    """Create a node that completed N days ago."""
    ts = _past_ts(days_ago)
    conn.execute(
        """
        MERGE (n:Node {id: $id})
        ON CREATE SET
            n.type = 'task',
            n.title = $id,
            n.status = 'completed',
            n.created_at = timestamp($ts),
            n.updated_at = timestamp($ts),
            n.status_since = timestamp($ts),
            n.content = NULL,
            n.file_path = NULL,
            n.properties = NULL,
            n.content_embedding = NULL
        ON MATCH SET
            n.status = 'completed',
            n.status_since = timestamp($ts)
        """,
        parameters={"id": node_id, "ts": ts},
    )


def _make_stuck_node(conn, node_id, days_stuck=16):
    """Create a task/goal that has been in_progress for N days."""
    ts = _past_ts(days_stuck)
    conn.execute(
        """
        MERGE (n:Node {id: $id})
        ON CREATE SET
            n.type = 'task',
            n.title = $id,
            n.status = 'in_progress',
            n.created_at = timestamp($ts),
            n.updated_at = timestamp($ts),
            n.status_since = timestamp($ts),
            n.content = NULL,
            n.file_path = NULL,
            n.properties = NULL,
            n.content_embedding = NULL
        ON MATCH SET
            n.status = 'in_progress',
            n.status_since = timestamp($ts)
        """,
        parameters={"id": node_id, "ts": ts},
    )


# ---------------------------------------------------------------------------
# compute_all_signals
# ---------------------------------------------------------------------------

class TestComputeAllSignals:
    def test_empty_graph_returns_all_signal_keys(self, db_conn):
        result = compute_all_signals(db_conn)
        assert "signals" in result
        assert "summary" in result
        signals = result["signals"]
        assert "stale" in signals
        assert "velocity_zero" in signals
        assert "recently_completed" in signals
        assert "dependency_changed" in signals
        assert "recurring_overdue" in signals

    def test_empty_graph_has_zero_summary_counts(self, db_conn):
        result = compute_all_signals(db_conn)
        summary = result["summary"]
        assert summary["stale_critical"] == 0
        assert summary["velocity_zero"] == 0
        assert summary["recently_completed"] == 0

    def test_generated_at_present(self, db_conn):
        result = compute_all_signals(db_conn)
        assert "generated_at" in result
        assert isinstance(result["generated_at"], str)


# ---------------------------------------------------------------------------
# compute_staleness
# ---------------------------------------------------------------------------

class TestComputeStaleness:
    def test_empty_graph_returns_empty(self, db_conn):
        assert compute_staleness(db_conn) == []

    def test_detects_stale_active_node(self, db_conn):
        _make_stale_node(db_conn, "stale1", node_type="goal", days_old=20)
        result = compute_staleness(db_conn)
        ids = [r["id"] for r in result]
        assert "stale1" in ids

    def test_fresh_node_not_in_stale(self, db_conn):
        create_node(db_conn, {
            "id": "fresh1",
            "type": "goal",
            "title": "Fresh",
            "status": "active",
        })
        result = compute_staleness(db_conn)
        ids = [r["id"] for r in result]
        assert "fresh1" not in ids

    def test_archived_node_excluded(self, db_conn):
        _make_stale_node(db_conn, "arch1", node_type="goal", days_old=30)
        # Archive it
        db_conn.execute(
            "MATCH (n:Node {id: 'arch1'}) SET n.status = 'archived'"
        )
        result = compute_staleness(db_conn)
        ids = [r["id"] for r in result]
        assert "arch1" not in ids

    def test_temporal_type_excluded(self, db_conn):
        _make_stale_node(db_conn, "ev_stale1", node_type="event", days_old=30)
        result = compute_staleness(db_conn)
        ids = [r["id"] for r in result]
        assert "ev_stale1" not in ids

    def test_stale_level_critical_for_30_plus_days(self, db_conn):
        _make_stale_node(db_conn, "crit1", node_type="goal", days_old=31)
        result = compute_staleness(db_conn)
        match = next((r for r in result if r["id"] == "crit1"), None)
        assert match is not None
        assert match["level"] == "CRITICAL"

    def test_stale_level_info_for_7_to_13_days(self, db_conn):
        _make_stale_node(db_conn, "info1", node_type="goal", days_old=8)
        result = compute_staleness(db_conn)
        match = next((r for r in result if r["id"] == "info1"), None)
        assert match is not None
        assert match["level"] == "INFO"


# ---------------------------------------------------------------------------
# compute_velocity_zero
# ---------------------------------------------------------------------------

class TestComputeVelocityZero:
    def test_empty_graph_returns_empty(self, db_conn):
        assert compute_velocity_zero(db_conn) == []

    def test_detects_stuck_task(self, db_conn):
        _make_stuck_node(db_conn, "stuck1", days_stuck=16)
        result = compute_velocity_zero(db_conn)
        ids = [r["id"] for r in result]
        assert "stuck1" in ids

    def test_fresh_task_not_detected(self, db_conn):
        create_node(db_conn, {
            "id": "fresh_task",
            "type": "task",
            "title": "Fresh Task",
            "status": "in_progress",
        })
        result = compute_velocity_zero(db_conn)
        ids = [r["id"] for r in result]
        assert "fresh_task" not in ids

    def test_blocked_status_threshold_is_7_days(self, db_conn):
        _make_stuck_node(db_conn, "blocked1", days_stuck=8)
        db_conn.execute(
            "MATCH (n:Node {id: 'blocked1'}) SET n.status = 'blocked'"
        )
        result = compute_velocity_zero(db_conn)
        ids = [r["id"] for r in result]
        assert "blocked1" in ids

    def test_completed_node_excluded(self, db_conn):
        _make_stuck_node(db_conn, "done1", days_stuck=20)
        db_conn.execute(
            "MATCH (n:Node {id: 'done1'}) SET n.status = 'completed'"
        )
        result = compute_velocity_zero(db_conn)
        ids = [r["id"] for r in result]
        assert "done1" not in ids

    def test_days_stuck_field_present(self, db_conn):
        _make_stuck_node(db_conn, "stuck2", days_stuck=16)
        result = compute_velocity_zero(db_conn)
        match = next((r for r in result if r["id"] == "stuck2"), None)
        assert match is not None
        assert "days_stuck" in match
        assert match["days_stuck"] >= 16


# ---------------------------------------------------------------------------
# compute_recently_completed
# ---------------------------------------------------------------------------

class TestComputeRecentlyCompleted:
    def test_empty_graph_returns_empty(self, db_conn):
        assert compute_recently_completed(db_conn) == []

    def test_finds_recently_completed_node(self, db_conn):
        _make_completed_node(db_conn, "done_recent", days_ago=1)
        result = compute_recently_completed(db_conn)
        ids = [r["id"] for r in result]
        assert "done_recent" in ids

    def test_old_completed_node_excluded(self, db_conn):
        _make_completed_node(db_conn, "done_old", days_ago=10)
        result = compute_recently_completed(db_conn)
        ids = [r["id"] for r in result]
        assert "done_old" not in ids

    def test_active_node_excluded(self, db_conn):
        create_node(db_conn, {
            "id": "active_node",
            "type": "task",
            "title": "Active",
            "status": "active",
        })
        result = compute_recently_completed(db_conn)
        ids = [r["id"] for r in result]
        assert "active_node" not in ids

    def test_result_has_completed_field(self, db_conn):
        _make_completed_node(db_conn, "done_field", days_ago=2)
        result = compute_recently_completed(db_conn)
        match = next((r for r in result if r["id"] == "done_field"), None)
        assert match is not None
        assert "completed" in match
