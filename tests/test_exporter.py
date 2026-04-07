"""Tests for brain_cli.exporter."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from brain_cli.exporter import (
    export_batch,
    export_cytoscape,
    export_json,
    _staleness_level,
    _serialize,
)
from brain_cli.writer import create_node, create_edge, execute_batch


class TestExportRoundTrip:
    def test_batch_round_trip_preserves_properties(self, db_conn, brain_dir):
        # Create node with nested properties
        create_node(db_conn, {
            "id": "n1",
            "type": "project",
            "title": "Demo",
            "properties": {"k": "v", "nested": {"a": 1, "b": [1, 2, 3]}},
        })

        # Export to backup file
        path, n_count, e_count = export_batch(db_conn)
        assert n_count == 1

        # Parse exported file directly -- properties must be a dict, not a string
        with open(path) as f:
            ops = json.load(f)
        node_op = next(op for op in ops if op["id"] == "n1")
        assert isinstance(node_op["properties"], dict)
        assert node_op["properties"]["nested"]["b"] == [1, 2, 3]

    def test_batch_round_trip_via_re_import(self, db_conn, brain_dir):
        # Create -> export -> wipe -> re-import -> verify
        create_node(db_conn, {
            "id": "rt1",
            "type": "project",
            "title": "RT",
            "properties": {"version": "1.0", "tags": ["a", "b"]},
        })
        path, _, _ = export_batch(db_conn)

        # Wipe and re-import
        db_conn.execute("MATCH (n:Node) DETACH DELETE n")
        with open(path) as f:
            ops = json.load(f)
        execute_batch(db_conn, ops)

        # Properties must still be a dict, not double-encoded JSON string
        result = db_conn.execute("MATCH (n:Node {id: 'rt1'}) RETURN n.properties")
        rows = []
        while result.has_next():
            rows.append(result.get_next())
        assert len(rows) == 1
        props_raw = rows[0][0]
        # If BUG-02 is back, this is a string of an escaped JSON string
        decoded = json.loads(props_raw) if isinstance(props_raw, str) else props_raw
        assert decoded == {"version": "1.0", "tags": ["a", "b"]}


class TestExportCytoscape:
    def test_empty_graph_exports_cleanly(self, db_conn, brain_dir):
        path, n, e = export_cytoscape(db_conn)
        with open(path) as f:
            graph = json.load(f)
        assert n == 0
        assert e == 0
        assert graph["elements"]["nodes"] == []
        assert graph["elements"]["edges"] == []
        assert "generated_at" in graph["meta"]

    def test_node_includes_staleness_metadata(self, db_conn, brain_dir):
        create_node(db_conn, {"id": "fresh", "type": "project", "title": "F"})
        path, n, e = export_cytoscape(db_conn)
        with open(path) as f:
            graph = json.load(f)
        node = graph["elements"]["nodes"][0]["data"]
        assert "staleness_level" in node
        assert "freshness_days" in node


class TestStalenessLevel:
    def test_unknown_when_both_none(self):
        level, days = _staleness_level(None, None)
        assert level == "unknown"
        assert days is None

    def test_uses_max_of_updated_and_verified(self):
        old = datetime.now(timezone.utc) - timedelta(days=60)
        recent = datetime.now(timezone.utc) - timedelta(days=1)
        level, days = _staleness_level(old, recent)
        assert level == "ok"
        assert days <= 1

    def test_critical_above_low_threshold(self):
        old = datetime.now(timezone.utc) - timedelta(days=45)
        level, days = _staleness_level(old, None)
        assert level == "critical"
        assert days >= 30


class TestSerialize:
    def test_serializes_datetime(self):
        dt = datetime(2026, 4, 7, 12, 0, 0, tzinfo=timezone.utc)
        assert _serialize(dt) == "2026-04-07T12:00:00+00:00"

    def test_raises_on_unsupported_type(self):
        with pytest.raises(TypeError):
            _serialize(object())
