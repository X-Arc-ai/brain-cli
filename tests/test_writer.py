"""Tests for brain_cli.writer -- node/edge CRUD and batch operations."""

from datetime import datetime, timezone, timedelta

import pytest

from brain_cli.writer import (
    create_node,
    update_node,
    archive_node,
    create_edge,
    end_edge,
    execute_batch,
    _ts_param,
)
from brain_cli.config import now
from brain_cli.utils import rows_to_dicts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_node(node_id, node_type="project", title=None, **kwargs):
    data = {"id": node_id, "type": node_type, "title": title or node_id}
    data.update(kwargs)
    return data


def _fetch_node(conn, node_id):
    result = conn.execute(
        "MATCH (n:Node {id: $id}) RETURN n.*",
        parameters={"id": node_id},
    )
    rows = rows_to_dicts(result)
    return rows[0] if rows else None


# ---------------------------------------------------------------------------
# create_node
# ---------------------------------------------------------------------------

class TestCreateNode:
    def test_create_minimal_node(self, db_conn):
        create_node(db_conn, _make_node("n1"))
        row = _fetch_node(db_conn, "n1")
        assert row is not None

    def test_created_node_has_correct_id(self, db_conn):
        create_node(db_conn, _make_node("n2", title="My Node"))
        row = _fetch_node(db_conn, "n2")
        assert row["n.id"] == "n2"

    def test_created_node_has_correct_title(self, db_conn):
        create_node(db_conn, _make_node("n3", title="Test Title"))
        row = _fetch_node(db_conn, "n3")
        assert row["n.title"] == "Test Title"

    def test_created_node_has_correct_type(self, db_conn):
        create_node(db_conn, _make_node("n4", node_type="person", title="Alice"))
        row = _fetch_node(db_conn, "n4")
        assert row["n.type"] == "person"

    def test_created_node_stores_status(self, db_conn):
        create_node(db_conn, _make_node("n5", status="active"))
        row = _fetch_node(db_conn, "n5")
        assert row["n.status"] == "active"

    def test_created_node_stores_content(self, db_conn):
        create_node(db_conn, _make_node("n6", content="Some content"))
        row = _fetch_node(db_conn, "n6")
        assert row["n.content"] == "Some content"

    def test_created_node_stores_file_path(self, db_conn):
        create_node(db_conn, _make_node("n7", file_path="docs/overview.md"))
        row = _fetch_node(db_conn, "n7")
        assert row["n.file_path"] == "docs/overview.md"

    def test_missing_id_raises_value_error(self, db_conn):
        with pytest.raises(ValueError, match="Missing required field: id"):
            create_node(db_conn, {"type": "project", "title": "Missing ID"})

    def test_missing_type_raises_value_error(self, db_conn):
        with pytest.raises(ValueError, match="Missing required field: type"):
            create_node(db_conn, {"id": "x", "title": "Missing Type"})

    def test_missing_title_raises_value_error(self, db_conn):
        with pytest.raises(ValueError, match="Missing required field: title"):
            create_node(db_conn, {"id": "x", "type": "project"})

    def test_invalid_status_raises_value_error(self, db_conn):
        with pytest.raises(ValueError, match="Invalid status"):
            create_node(db_conn, _make_node("n8", status="bad_status"))

    def test_create_node_idempotent_on_merge(self, db_conn):
        # Second call with same ID should not raise (MERGE semantics)
        create_node(db_conn, _make_node("n9", title="Original"))
        create_node(db_conn, _make_node("n9", title="Updated via merge"))
        row = _fetch_node(db_conn, "n9")
        assert row is not None

    def test_create_node_with_explicit_timestamps(self, db_conn):
        old_ts = datetime(2020, 1, 1, tzinfo=timezone.utc)
        create_node(db_conn, _make_node(
            "n10",
            created_at=old_ts,
            updated_at=old_ts,
        ))
        row = _fetch_node(db_conn, "n10")
        assert row is not None


# ---------------------------------------------------------------------------
# update_node
# ---------------------------------------------------------------------------

class TestUpdateNode:
    def test_update_title(self, db_conn):
        create_node(db_conn, _make_node("u1", title="Old Title"))
        update_node(db_conn, {"id": "u1", "title": "New Title"})
        row = _fetch_node(db_conn, "u1")
        assert row["n.title"] == "New Title"

    def test_update_status(self, db_conn):
        create_node(db_conn, _make_node("u2", status="pending"))
        update_node(db_conn, {"id": "u2", "status": "completed"})
        row = _fetch_node(db_conn, "u2")
        assert row["n.status"] == "completed"

    def test_update_content(self, db_conn):
        create_node(db_conn, _make_node("u3"))
        update_node(db_conn, {"id": "u3", "content": "Updated content"})
        row = _fetch_node(db_conn, "u3")
        assert row["n.content"] == "Updated content"

    def test_update_nonexistent_node_raises(self, db_conn):
        with pytest.raises(ValueError, match="Node not found"):
            update_node(db_conn, {"id": "ghost", "title": "Ghost"})

    def test_update_missing_id_raises(self, db_conn):
        with pytest.raises(ValueError, match="Missing required field: id"):
            update_node(db_conn, {"title": "No ID"})

    def test_update_invalid_status_raises(self, db_conn):
        create_node(db_conn, _make_node("u4"))
        with pytest.raises(ValueError, match="Invalid status"):
            update_node(db_conn, {"id": "u4", "status": "flying"})

    def test_update_immutable_type_raises(self, db_conn):
        create_node(db_conn, {"id": "ev1", "type": "event", "title": "An event"})
        with pytest.raises(ValueError, match="Cannot update immutable node type"):
            update_node(db_conn, {"id": "ev1", "title": "New Title"})

    def test_update_immutable_type_with_maintenance_status(self, db_conn):
        create_node(db_conn, {"id": "ev2", "type": "event", "title": "An event"})
        # maintenance=True allows status and properties updates
        update_node(db_conn, {"id": "ev2", "status": "archived"}, maintenance=True)
        row = _fetch_node(db_conn, "ev2")
        assert row["n.status"] == "archived"

    def test_update_immutable_with_maintenance_rejects_title(self, db_conn):
        create_node(db_conn, {"id": "ev3", "type": "event", "title": "An event"})
        with pytest.raises(ValueError, match="Unexpected fields"):
            update_node(db_conn, {"id": "ev3", "title": "New Title"}, maintenance=True)

    def test_update_bumps_updated_at(self, db_conn):
        old_ts = datetime(2020, 1, 1, tzinfo=timezone.utc)
        create_node(db_conn, _make_node("u5", updated_at=old_ts))
        update_node(db_conn, {"id": "u5", "title": "Updated"})
        row = _fetch_node(db_conn, "u5")
        # updated_at should now be recent
        updated = row["n.updated_at"]
        if hasattr(updated, "tzinfo") and updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        assert updated > old_ts


# ---------------------------------------------------------------------------
# archive_node
# ---------------------------------------------------------------------------

class TestArchiveNode:
    def test_archive_sets_status_to_archived(self, db_conn):
        create_node(db_conn, _make_node("a1", status="active"))
        archive_node(db_conn, "a1")
        row = _fetch_node(db_conn, "a1")
        assert row["n.status"] == "archived"

    def test_archive_nonexistent_node_is_silent(self, db_conn):
        # Kuzu MATCH + SET on missing node is a no-op (no error)
        archive_node(db_conn, "does_not_exist")


# ---------------------------------------------------------------------------
# create_edge
# ---------------------------------------------------------------------------

class TestCreateEdge:
    def test_create_edge_between_existing_nodes(self, db_conn):
        create_node(db_conn, _make_node("src1", node_type="person", title="Alice"))
        create_node(db_conn, _make_node("dst1", node_type="project", title="Proj"))
        create_edge(db_conn, {"from": "src1", "to": "dst1", "verb": "works on"})
        result = db_conn.execute(
            "MATCH (a:Node {id: 'src1'})-[e:Edge]->(b:Node {id: 'dst1'}) RETURN e.verb"
        )
        rows = rows_to_dicts(result)
        assert len(rows) == 1
        assert rows[0]["e.verb"] == "works on"

    def test_create_edge_with_missing_from_node_raises(self, db_conn):
        create_node(db_conn, _make_node("dst2", node_type="project", title="Proj"))
        with pytest.raises(ValueError, match="node.s. not found"):
            create_edge(db_conn, {"from": "ghost", "to": "dst2", "verb": "depends on"})

    def test_create_edge_with_missing_to_node_raises(self, db_conn):
        create_node(db_conn, _make_node("src2", node_type="person", title="Bob"))
        with pytest.raises(ValueError, match="node.s. not found"):
            create_edge(db_conn, {"from": "src2", "to": "ghost", "verb": "depends on"})

    def test_create_edge_missing_verb_raises(self, db_conn):
        create_node(db_conn, _make_node("src3", node_type="person", title="Carol"))
        create_node(db_conn, _make_node("dst3", node_type="project", title="P2"))
        with pytest.raises(ValueError, match="Missing required edge field"):
            create_edge(db_conn, {"from": "src3", "to": "dst3"})

    def test_create_edge_missing_from_field_raises(self, db_conn):
        with pytest.raises(ValueError, match="Missing required edge field"):
            create_edge(db_conn, {"to": "dst3", "verb": "works on"})

    def test_create_edge_error_lists_received_keys(self, db_conn):
        with pytest.raises(ValueError, match=r"Got keys"):
            create_edge(db_conn, {"from_id": "x", "to_id": "y", "verb": "z"})

    def test_create_edge_stores_note(self, db_conn):
        create_node(db_conn, _make_node("src4", node_type="person", title="Dan"))
        create_node(db_conn, _make_node("dst4", node_type="project", title="P3"))
        create_edge(db_conn, {
            "from": "src4", "to": "dst4", "verb": "manages",
            "note": "lead since Jan",
        })
        result = db_conn.execute(
            "MATCH (a:Node {id: 'src4'})-[e:Edge]->(b:Node {id: 'dst4'}) RETURN e.note"
        )
        rows = rows_to_dicts(result)
        assert rows[0]["e.note"] == "lead since Jan"


# ---------------------------------------------------------------------------
# end_edge
# ---------------------------------------------------------------------------

class TestEndEdge:
    def test_end_edge_sets_until(self, db_conn):
        create_node(db_conn, _make_node("se1", node_type="person", title="Eve"))
        create_node(db_conn, _make_node("se2", node_type="project", title="P4"))
        create_edge(db_conn, {"from": "se1", "to": "se2", "verb": "leads"})
        end_edge(db_conn, "se1", "se2", "leads")
        result = db_conn.execute(
            "MATCH (a:Node {id: 'se1'})-[e:Edge]->(b:Node {id: 'se2'}) RETURN e.until"
        )
        rows = rows_to_dicts(result)
        assert rows[0]["e.until"] is not None


# ---------------------------------------------------------------------------
# execute_batch
# ---------------------------------------------------------------------------

class TestExecuteBatch:
    def test_batch_create_nodes(self, db_conn):
        ops = [
            {"op": "create_node", "id": "b1", "type": "project", "title": "Batch Node 1"},
            {"op": "create_node", "id": "b2", "type": "person", "title": "Batch Node 2"},
        ]
        results = execute_batch(db_conn, ops)
        # Last element is summary
        summary = results[-1]["summary"]
        assert summary["created_nodes"] == 2

    def test_batch_create_edge(self, db_conn):
        create_node(db_conn, _make_node("be1", node_type="person", title="Frank"))
        create_node(db_conn, _make_node("be2", node_type="project", title="P5"))
        ops = [{"op": "create_edge", "from": "be1", "to": "be2", "verb": "owns"}]
        results = execute_batch(db_conn, ops)
        summary = results[-1]["summary"]
        assert summary["created_edges"] == 1

    def test_batch_mixed_operations(self, db_conn):
        create_node(db_conn, _make_node("bm1", node_type="project", title="Old"))
        ops = [
            {"op": "create_node", "id": "bm2", "type": "person", "title": "Grace"},
            {"op": "update_node", "id": "bm1", "title": "New"},
        ]
        results = execute_batch(db_conn, ops)
        summary = results[-1]["summary"]
        assert summary["total"] == 2

    def test_batch_update_node_status(self, db_conn):
        create_node(db_conn, _make_node("bst1", status="pending"))
        ops = [{"op": "update_node", "id": "bst1", "status": "completed"}]
        execute_batch(db_conn, ops)
        row = _fetch_node(db_conn, "bst1")
        assert row["n.status"] == "completed"

    def test_batch_invalid_op_raises(self, db_conn):
        with pytest.raises(ValueError, match="unknown op"):
            execute_batch(db_conn, [{"op": "fly_to_moon", "id": "x"}])

    def test_batch_returns_summary_as_last_element(self, db_conn):
        ops = [{"op": "create_node", "id": "bs1", "type": "project", "title": "T"}]
        results = execute_batch(db_conn, ops)
        last = results[-1]
        assert "summary" in last
        assert "total" in last["summary"]
        assert "created_nodes" in last["summary"]
        assert "created_edges" in last["summary"]

    def test_batch_operation_error_propagates(self, db_conn):
        # create_edge referencing non-existent node should fail
        ops = [{"op": "create_edge", "from": "ghost1", "to": "ghost2", "verb": "v"}]
        with pytest.raises(ValueError):
            execute_batch(db_conn, ops)

    def test_empty_batch_returns_zero_summary(self, db_conn):
        results = execute_batch(db_conn, [])
        summary = results[-1]["summary"]
        assert summary["total"] == 0
        assert summary["created_nodes"] == 0
        assert summary["created_edges"] == 0
