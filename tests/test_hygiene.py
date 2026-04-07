"""Tests for brain_cli.hygiene -- duplicates, orphans, completeness, verbs."""

import os

import pytest

from brain_cli.writer import create_node, create_edge
from brain_cli.hygiene import (
    find_duplicates,
    find_orphans,
    check_completeness,
    check_content_drift,
    check_file_paths,
    check_operational_readiness,
    audit_verbs,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node(node_id, node_type="project", title=None, **kwargs):
    d = {"id": node_id, "type": node_type, "title": title or node_id}
    d.update(kwargs)
    return d


def _edge(from_id, to_id, verb):
    return {"from": from_id, "to": to_id, "verb": verb}


# ---------------------------------------------------------------------------
# find_duplicates
# ---------------------------------------------------------------------------

class TestFindDuplicates:
    def test_empty_graph_no_duplicates(self, db_conn):
        assert find_duplicates(db_conn) == []

    def test_detects_same_title_same_type(self, db_conn):
        create_node(db_conn, _node("dup1a", title="Duplicate Title"))
        create_node(db_conn, _node("dup1b", title="Duplicate Title"))
        result = find_duplicates(db_conn)
        assert len(result) >= 1
        titles = [r["title"] for r in result]
        assert "Duplicate Title" in titles

    def test_same_title_different_type_not_duplicate(self, db_conn):
        create_node(db_conn, _node("dup2a", node_type="project", title="Shared Name"))
        create_node(db_conn, _node("dup2b", node_type="person", title="Shared Name"))
        result = find_duplicates(db_conn)
        pairs = [(r["id_a"], r["id_b"]) for r in result]
        assert ("dup2a", "dup2b") not in pairs

    def test_unique_titles_no_duplicates(self, db_conn):
        create_node(db_conn, _node("dup3a", title="Title Alpha"))
        create_node(db_conn, _node("dup3b", title="Title Beta"))
        result = find_duplicates(db_conn)
        assert result == []

    def test_duplicate_result_has_expected_fields(self, db_conn):
        create_node(db_conn, _node("dup4a", title="Same Thing"))
        create_node(db_conn, _node("dup4b", title="Same Thing"))
        result = find_duplicates(db_conn)
        assert len(result) >= 1
        row = result[0]
        assert "id_a" in row
        assert "id_b" in row
        assert "title" in row
        assert "type" in row


# ---------------------------------------------------------------------------
# find_orphans
# ---------------------------------------------------------------------------

class TestFindOrphans:
    def test_empty_graph_no_orphans(self, db_conn):
        assert find_orphans(db_conn) == []

    def test_isolated_node_is_orphan(self, db_conn):
        create_node(db_conn, _node("orp1", title="Lonely Node"))
        result = find_orphans(db_conn)
        ids = [r["n.id"] for r in result]
        assert "orp1" in ids

    def test_connected_node_not_orphan(self, db_conn):
        create_node(db_conn, _node("orp2", node_type="project", title="Proj"))
        create_node(db_conn, _node("orp3", node_type="person", title="Person"))
        create_edge(db_conn, _edge("orp3", "orp2", "works on"))
        result = find_orphans(db_conn)
        ids = [r["n.id"] for r in result]
        assert "orp2" not in ids
        assert "orp3" not in ids

    def test_orphan_result_has_expected_fields(self, db_conn):
        create_node(db_conn, _node("orp4", title="Orphaned"))
        result = find_orphans(db_conn)
        assert len(result) >= 1
        row = next(r for r in result if r["n.id"] == "orp4")
        assert "n.id" in row
        assert "n.title" in row
        assert "n.type" in row


# ---------------------------------------------------------------------------
# check_completeness
# ---------------------------------------------------------------------------

class TestCheckCompleteness:
    def test_empty_graph_no_violations(self, db_conn):
        assert check_completeness(db_conn) == []

    def test_goal_without_person_edge_is_violation(self, db_conn):
        create_node(db_conn, _node("g1", node_type="goal", title="Goal without owner",
                                   status="active"))
        result = check_completeness(db_conn)
        ids = [r["node_id"] for r in result]
        assert "g1" in ids

    def test_goal_with_person_edge_passes(self, db_conn):
        create_node(db_conn, _node("g2", node_type="goal", title="Owned Goal",
                                   status="active"))
        create_node(db_conn, _node("p2", node_type="person", title="Owner"))
        create_edge(db_conn, _edge("g2", "p2", "assigned to"))
        # goal also needs "goal for" edge
        create_node(db_conn, _node("proj2", node_type="project", title="Proj"))
        create_edge(db_conn, _edge("g2", "proj2", "goal for"))
        result = check_completeness(db_conn)
        # g2 should not appear in violations
        ids = [r["node_id"] for r in result]
        assert "g2" not in ids

    def test_task_without_person_is_violation(self, db_conn):
        create_node(db_conn, _node("t1", node_type="task", title="Unassigned Task",
                                   status="active"))
        result = check_completeness(db_conn)
        ids = [r["node_id"] for r in result]
        assert "t1" in ids

    def test_archived_goal_excluded(self, db_conn):
        create_node(db_conn, _node("g3", node_type="goal", title="Archived Goal",
                                   status="archived"))
        result = check_completeness(db_conn)
        ids = [r["node_id"] for r in result]
        assert "g3" not in ids

    def test_violation_has_required_fields(self, db_conn):
        create_node(db_conn, _node("t2", node_type="task", title="Task No Owner",
                                   status="pending"))
        result = check_completeness(db_conn)
        match = next((r for r in result if r["node_id"] == "t2"), None)
        assert match is not None
        assert "node_id" in match
        assert "node_title" in match
        assert "node_type" in match
        assert "rule" in match
        assert "missing_verbs" in match


# ---------------------------------------------------------------------------
# audit_verbs
# ---------------------------------------------------------------------------

class TestAuditVerbs:
    def test_empty_graph_returns_empty(self, db_conn):
        assert audit_verbs(db_conn) == []

    def test_counts_verbs(self, db_conn):
        create_node(db_conn, _node("av1", node_type="person", title="Alice"))
        create_node(db_conn, _node("av2", node_type="project", title="Proj"))
        create_edge(db_conn, _edge("av1", "av2", "leads"))
        result = audit_verbs(db_conn)
        verbs = {r["verb"]: r["count"] for r in result}
        assert "leads" in verbs
        assert verbs["leads"] == 1

    def test_multiple_same_verb_counted(self, db_conn):
        create_node(db_conn, _node("av3", node_type="person", title="Bob"))
        create_node(db_conn, _node("av4", node_type="project", title="P1"))
        create_node(db_conn, _node("av5", node_type="project", title="P2"))
        create_edge(db_conn, _edge("av3", "av4", "works on"))
        create_edge(db_conn, _edge("av3", "av5", "works on"))
        result = audit_verbs(db_conn)
        verbs = {r["verb"]: r["count"] for r in result}
        assert verbs.get("works on", 0) == 2

    def test_result_sorted_by_count_desc(self, db_conn):
        create_node(db_conn, _node("av6", node_type="person", title="Carol"))
        create_node(db_conn, _node("av7", node_type="project", title="P3"))
        create_node(db_conn, _node("av8", node_type="project", title="P4"))
        create_edge(db_conn, _edge("av6", "av7", "manages"))
        create_edge(db_conn, _edge("av6", "av8", "manages"))
        # Second verb with only one edge
        create_node(db_conn, _node("av9", node_type="project", title="P5"))
        create_edge(db_conn, _edge("av6", "av9", "leads"))
        result = audit_verbs(db_conn)
        counts = [r["count"] for r in result]
        assert counts == sorted(counts, reverse=True)


# ---------------------------------------------------------------------------
# check_file_paths
# ---------------------------------------------------------------------------

class TestCheckFilePaths:
    def test_active_structural_node_without_file_path_flagged(self, db_conn):
        create_node(db_conn, _node(
            "fp1", node_type="project", title="P", status="active"
        ))
        violations = check_file_paths(db_conn)
        assert any(v["node_id"] == "fp1" for v in violations)

    def test_node_with_existing_file_path_passes(self, tmp_path, db_conn, brain_dir, monkeypatch):
        f = tmp_path / "exists.md"
        f.write_text("hi")
        monkeypatch.setenv("BRAIN_PROJECT_ROOT", str(tmp_path))
        create_node(db_conn, _node(
            "fp2", node_type="project", title="P2",
            status="active", file_path="exists.md",
        ))
        violations = check_file_paths(db_conn)
        # fp2 should not appear
        broken = [v for v in violations
                  if v["node_id"] == "fp2"
                  and v.get("check") in ("missing_file_path", "broken_file_path")]
        assert broken == []

    def test_node_with_broken_file_path_flagged(self, db_conn, brain_dir, monkeypatch, tmp_path):
        monkeypatch.setenv("BRAIN_PROJECT_ROOT", str(tmp_path))
        create_node(db_conn, _node(
            "fp3", node_type="project", title="P3",
            status="active", file_path="missing.md",
        ))
        violations = check_file_paths(db_conn)
        assert any(
            v["node_id"] == "fp3" and v.get("check") == "broken_file_path"
            for v in violations
        )


# ---------------------------------------------------------------------------
# check_content_drift
# ---------------------------------------------------------------------------

class TestCheckContentDrift:
    def test_thin_brain_content_detected(self, tmp_path, db_conn, brain_dir, monkeypatch):
        # File 3x+ longer than brain content (and brain is < 500 chars)
        f = tmp_path / "doc.md"
        f.write_text("# H1\n\n" + ("This is a very long document. " * 100))
        monkeypatch.setenv("BRAIN_PROJECT_ROOT", str(tmp_path))
        create_node(db_conn, _node(
            "doc1", node_type="project", title="Doc",
            status="active", file_path="doc.md",
            content="short",
        ))
        violations = check_content_drift(db_conn)
        assert any(
            v["node_id"] == "doc1" and v.get("check") == "thin_brain_content"
            for v in violations
        )


# ---------------------------------------------------------------------------
# check_operational_readiness
# ---------------------------------------------------------------------------

class TestCheckOperationalReadiness:
    def test_goal_without_tasks_or_blockers_flagged(self, db_conn):
        create_node(db_conn, _node("og1", node_type="goal", title="G", status="active"))
        violations = check_operational_readiness(db_conn)
        assert any(v["node_id"] == "og1" for v in violations)

    def test_goal_with_outgoing_decomposition_passes(self, db_conn):
        create_node(db_conn, _node("og2", node_type="goal", title="G2", status="active"))
        create_node(db_conn, _node("ot2", node_type="task", title="T2", status="active"))
        create_edge(db_conn, _edge("og2", "ot2", "has task"))
        violations = check_operational_readiness(db_conn)
        assert all(v["node_id"] != "og2" for v in violations)

    def test_goal_with_blocker_passes(self, db_conn):
        create_node(db_conn, _node("og3", node_type="goal", title="G3", status="active"))
        create_node(db_conn, _node("ob3", node_type="blocker", title="B3", status="active"))
        create_edge(db_conn, _edge("og3", "ob3", "blocked by"))
        violations = check_operational_readiness(db_conn)
        assert all(v["node_id"] != "og3" for v in violations)

    def test_pending_decision_without_edges_flagged(self, db_conn):
        create_node(db_conn, _node("od1", node_type="decision", title="D", status="pending"))
        violations = check_operational_readiness(db_conn)
        assert any(v["node_id"] == "od1" for v in violations)
