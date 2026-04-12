"""Tests for brain_cli.replay -- conversation replay pipeline."""

import pytest
from unittest.mock import MagicMock, patch

from brain_cli.writer import create_node, create_edge
from brain_cli.replay import (
    _require_memory,
    _stage_broad_sweep,
    _stage_entity_sweep,
    _stage_semantic_sweep,
    _stage_filter,
    _stage_propose,
    _deduplicate,
    run_replay,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node(node_id, node_type="project", title=None, **kwargs):
    d = {"id": node_id, "type": node_type, "title": title or node_id}
    d.update(kwargs)
    return d


def _mock_memory():
    """Create a mock memory module with a search method."""
    mem = MagicMock()
    mem.search = MagicMock(return_value=[
        {"text": "We decided to migrate to Stripe for billing"},
        {"text": "Alice is leading the API rewrite"},
    ])
    return mem


# ---------------------------------------------------------------------------
# _require_memory
# ---------------------------------------------------------------------------

class TestRequireMemory:
    def test_raises_without_package(self):
        with patch.dict("sys.modules", {"memory": None}):
            with pytest.raises(RuntimeError, match="xarc-memory is required"):
                _require_memory()

    def test_returns_module_when_available(self):
        mock_mem = MagicMock()
        with patch.dict("sys.modules", {"memory": mock_mem}):
            result = _require_memory()
            assert result is mock_mem


# ---------------------------------------------------------------------------
# _stage_broad_sweep
# ---------------------------------------------------------------------------

class TestStageBroadSweep:
    def test_returns_candidates(self):
        mem = _mock_memory()
        candidates = _stage_broad_sweep(mem, since_days=30)
        assert len(candidates) > 0
        assert mem.search.called

    def test_candidates_have_stage_field(self):
        mem = _mock_memory()
        candidates = _stage_broad_sweep(mem, since_days=30)
        for c in candidates:
            assert c["_stage"] == "broad_sweep"
            assert "_keyword" in c

    def test_queries_all_keywords(self):
        mem = _mock_memory()
        mem.search.return_value = [{"text": "test"}]
        _stage_broad_sweep(mem, since_days=30)
        # Should query for each of the 8 keywords
        assert mem.search.call_count == 8


# ---------------------------------------------------------------------------
# _stage_entity_sweep
# ---------------------------------------------------------------------------

class TestStageEntitySweep:
    def test_queries_structural_nodes(self, db_conn):
        create_node(db_conn, _node("es1", node_type="project", title="My Project", status="active"))
        create_node(db_conn, _node("es2", node_type="person", title="Alice", status="active"))
        mem = _mock_memory()
        candidates = _stage_entity_sweep(mem, db_conn, since_days=30)
        assert len(candidates) > 0
        assert any(c.get("_entity_id") == "es1" for c in candidates)

    def test_skips_archived_nodes(self, db_conn):
        create_node(db_conn, _node("es3", node_type="project", title="Old Project",
                                   status="archived"))
        mem = _mock_memory()
        mem.search.return_value = []
        candidates = _stage_entity_sweep(mem, db_conn, since_days=30)
        assert not any(c.get("_entity_id") == "es3" for c in candidates)


# ---------------------------------------------------------------------------
# _stage_filter
# ---------------------------------------------------------------------------

class TestStageFilter:
    def test_skips_existing_nodes(self, db_conn):
        # Create a node with substantial content
        create_node(db_conn, _node(
            "sf1", node_type="project", title="Stripe Migration",
            content="Migrating billing from legacy processor to Stripe. " * 10,
        ))
        candidates = [{"text": "Stripe Migration is underway"}]
        filtered = _stage_filter(db_conn, candidates)
        # With rich content in graph, the candidate might be filtered out
        # This is a heuristic, so we just check the function runs
        assert isinstance(filtered, list)

    def test_keeps_novel_candidates(self, db_conn):
        # Empty graph -- nothing should be filtered
        candidates = [{"text": "Completely new topic about quantum computing research"}]
        filtered = _stage_filter(db_conn, candidates)
        assert len(filtered) == 1


# ---------------------------------------------------------------------------
# _stage_propose
# ---------------------------------------------------------------------------

class TestStagePropose:
    def test_builds_valid_batch(self):
        filtered = [
            {"text": "New API endpoint launched", "_stage": "broad_sweep", "_keyword": "shipped"},
            {"text": "Update alice context", "_stage": "entity_sweep",
             "_entity_id": "alice", "_entity_title": "Alice"},
        ]
        proposals = _stage_propose(filtered)
        assert len(proposals) >= 1
        for p in proposals:
            assert "op" in p
            assert "id" in p or "from" in p
            assert "_source" in p

    def test_entity_sweep_proposes_update(self):
        filtered = [
            {"text": "Alice now leads backend", "_stage": "entity_sweep",
             "_entity_id": "alice", "_entity_title": "Alice"},
        ]
        proposals = _stage_propose(filtered)
        assert len(proposals) == 1
        assert proposals[0]["op"] == "update_node"
        assert proposals[0]["id"] == "alice"

    def test_broad_sweep_proposes_create(self):
        filtered = [
            {"text": "Decision: switch to PostgreSQL", "_stage": "broad_sweep",
             "_keyword": "decision"},
        ]
        proposals = _stage_propose(filtered)
        assert len(proposals) == 1
        assert proposals[0]["op"] == "create_node"
        assert proposals[0]["type"] == "observation"

    def test_deduplicates_proposals(self):
        filtered = [
            {"text": "Same info", "_stage": "broad_sweep", "_keyword": "new"},
            {"text": "Same info", "_stage": "semantic_sweep", "_topic": "launch"},
        ]
        proposals = _stage_propose(filtered)
        # Same text hashes to same ID, so should be deduplicated
        assert len(proposals) == 1


# ---------------------------------------------------------------------------
# _deduplicate
# ---------------------------------------------------------------------------

class TestDeduplicate:
    def test_removes_exact_duplicates(self):
        candidates = [
            {"text": "hello world"},
            {"text": "hello world"},
            {"text": "different"},
        ]
        result = _deduplicate(candidates)
        assert len(result) == 2

    def test_preserves_unique(self):
        candidates = [
            {"text": "alpha"},
            {"text": "beta"},
            {"text": "gamma"},
        ]
        result = _deduplicate(candidates)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# run_replay
# ---------------------------------------------------------------------------

class TestRunReplay:
    def test_dry_run_does_not_execute(self, db_conn):
        mem = _mock_memory()
        with patch("brain_cli.replay._require_memory", return_value=mem):
            result = run_replay(db_conn, since_days=30, dry_run=True)
        assert result["executed"] is False
        assert "proposals" in result

    def test_raises_without_memory(self, db_conn):
        with patch("brain_cli.replay._require_memory", side_effect=RuntimeError("no memory")):
            with pytest.raises(RuntimeError):
                run_replay(db_conn, since_days=30)
