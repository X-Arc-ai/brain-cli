"""Tests for brain_cli.reader -- queries, scan, context, search."""

import pytest

from brain_cli.writer import create_node, create_edge
from brain_cli.reader import (
    get_node,
    get_context,
    scan_subgraph,
    search_nodes,
    query_chain,
    get_stats,
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
# get_node
# ---------------------------------------------------------------------------

class TestGetNode:
    def test_returns_node_by_id(self, db_conn):
        create_node(db_conn, _node("gn1", title="Alpha"))
        node = get_node(db_conn, "gn1")
        assert node is not None
        assert node["id"] == "gn1"
        assert node["title"] == "Alpha"

    def test_returns_none_for_missing_node(self, db_conn):
        assert get_node(db_conn, "does_not_exist") is None

    def test_includes_edges_out(self, db_conn):
        create_node(db_conn, _node("gn2", node_type="person", title="Bob"))
        create_node(db_conn, _node("gn3", node_type="project", title="Proj"))
        create_edge(db_conn, _edge("gn2", "gn3", "works on"))
        node = get_node(db_conn, "gn2")
        assert len(node["edges_out"]) == 1
        assert node["edges_out"][0]["e.verb"] == "works on"

    def test_includes_edges_in(self, db_conn):
        create_node(db_conn, _node("gn4", node_type="person", title="Carol"))
        create_node(db_conn, _node("gn5", node_type="project", title="Proj2"))
        create_edge(db_conn, _edge("gn4", "gn5", "manages"))
        node = get_node(db_conn, "gn5")
        assert len(node["edges_in"]) == 1
        assert node["edges_in"][0]["e.verb"] == "manages"

    def test_empty_edges_when_isolated(self, db_conn):
        create_node(db_conn, _node("gn6"))
        node = get_node(db_conn, "gn6")
        assert node["edges_out"] == []
        assert node["edges_in"] == []

    def test_properties_parsed_from_json(self, db_conn):
        import json
        create_node(db_conn, _node("gn7", properties={"key": "value"}))
        node = get_node(db_conn, "gn7")
        assert node["properties"] == {"key": "value"}


# ---------------------------------------------------------------------------
# scan_subgraph
# ---------------------------------------------------------------------------

class TestScanSubgraph:
    def test_returns_root_node(self, db_conn):
        create_node(db_conn, _node("sc1", title="Root"))
        result = scan_subgraph(db_conn, "sc1")
        assert result is not None
        assert result["root"]["id"] == "sc1"
        assert result["root"]["title"] == "Root"

    def test_returns_none_for_missing_node(self, db_conn):
        assert scan_subgraph(db_conn, "ghost_id") is None

    def test_hop_1_nodes_included(self, db_conn):
        create_node(db_conn, _node("sc2", node_type="project", title="Root2"))
        create_node(db_conn, _node("sc3", node_type="person", title="Person"))
        create_edge(db_conn, _edge("sc3", "sc2", "works on"))
        result = scan_subgraph(db_conn, "sc2")
        assert 1 in result["nodes_by_hop"]
        hop1_ids = [n["id"] for n in result["nodes_by_hop"][1]]
        assert "sc3" in hop1_ids

    def test_total_nodes_count_correct(self, db_conn):
        create_node(db_conn, _node("sc4", node_type="project", title="P"))
        create_node(db_conn, _node("sc5", node_type="person", title="Q"))
        create_edge(db_conn, _edge("sc5", "sc4", "contributes to"))
        result = scan_subgraph(db_conn, "sc4")
        assert result["total_nodes"] == 2

    def test_edges_list_included(self, db_conn):
        create_node(db_conn, _node("sc6", node_type="project", title="P2"))
        create_node(db_conn, _node("sc7", node_type="person", title="R"))
        create_edge(db_conn, _edge("sc7", "sc6", "leads"))
        result = scan_subgraph(db_conn, "sc6")
        assert len(result["edges"]) >= 1

    def test_isolated_node_has_no_hops(self, db_conn):
        create_node(db_conn, _node("sc8"))
        result = scan_subgraph(db_conn, "sc8")
        assert result["nodes_by_hop"] == {}

    def test_hop_1_includes_content(self, db_conn):
        create_node(db_conn, _node("sc9", node_type="project", title="Root3"))
        create_node(db_conn, _node("sc10", node_type="person", title="S",
                                   content="Person content"))
        create_edge(db_conn, _edge("sc10", "sc9", "works on"))
        result = scan_subgraph(db_conn, "sc9")
        hop1 = result["nodes_by_hop"][1]
        match = next((n for n in hop1 if n["id"] == "sc10"), None)
        assert match is not None
        assert "content" in match


# ---------------------------------------------------------------------------
# get_context
# ---------------------------------------------------------------------------

class TestGetContext:
    def test_returns_root_with_connected(self, db_conn):
        create_node(db_conn, _node("ctx1", node_type="project", title="Proj"))
        create_node(db_conn, _node("ctx2", node_type="person", title="Alice"))
        create_edge(db_conn, _edge("ctx2", "ctx1", "owns"))
        result = get_context(db_conn, "ctx1")
        assert result is not None
        assert result["id"] == "ctx1"
        assert result["connected_count"] == 1

    def test_returns_none_for_missing(self, db_conn):
        assert get_context(db_conn, "ghost") is None

    def test_connected_grouped_by_type(self, db_conn):
        create_node(db_conn, _node("ctx3", node_type="project", title="Proj2"))
        create_node(db_conn, _node("ctx4", node_type="person", title="Bob"))
        create_edge(db_conn, _edge("ctx4", "ctx3", "works on"))
        result = get_context(db_conn, "ctx3")
        assert "person" in result["connected"]


# ---------------------------------------------------------------------------
# search_nodes
# ---------------------------------------------------------------------------

class TestSearchNodes:
    def test_finds_by_title(self, db_conn):
        create_node(db_conn, _node("sn1", title="Unique Searchable Title"))
        results = search_nodes(db_conn, "Unique Searchable")
        ids = [r["n.id"] for r in results]
        assert "sn1" in ids

    def test_finds_by_content(self, db_conn):
        create_node(db_conn, _node("sn2", content="special content marker"))
        results = search_nodes(db_conn, "special content marker")
        ids = [r["n.id"] for r in results]
        assert "sn2" in ids

    def test_finds_by_id_substring(self, db_conn):
        create_node(db_conn, _node("unique-id-xyz"))
        results = search_nodes(db_conn, "unique-id-xyz")
        ids = [r["n.id"] for r in results]
        assert "unique-id-xyz" in ids

    def test_empty_result_for_nonexistent_query(self, db_conn):
        results = search_nodes(db_conn, "xyzzy_no_such_thing_12345")
        assert results == []

    def test_type_filter_limits_results(self, db_conn):
        create_node(db_conn, _node("sn3", node_type="project", title="Filtered Proj"))
        create_node(db_conn, _node("sn4", node_type="person", title="Filtered Person"))
        results = search_nodes(db_conn, "Filtered", type_filter="project")
        types = {r["n.type"] for r in results}
        assert types == {"project"}

    def test_match_snippet_included_for_content_match(self, db_conn):
        create_node(db_conn, _node("sn5", content="the needle is here in content"))
        results = search_nodes(db_conn, "needle")
        match = next((r for r in results if r["n.id"] == "sn5"), None)
        assert match is not None
        assert "match_snippet" in match
        assert "needle" in match["match_snippet"]


# ---------------------------------------------------------------------------
# query_chain
# ---------------------------------------------------------------------------

class TestQueryChain:
    def test_empty_chain_for_isolated_node(self, db_conn):
        create_node(db_conn, _node("qc1"))
        result = query_chain(db_conn, "qc1")
        assert result == []

    def test_follows_depends_on_edge(self, db_conn):
        create_node(db_conn, _node("qc2", node_type="task", title="Task"))
        create_node(db_conn, _node("qc3", node_type="goal", title="Blocker"))
        create_edge(db_conn, {"from": "qc2", "to": "qc3", "verb": "depends on"})
        result = query_chain(db_conn, "qc2")
        ids = [r["dep.id"] for r in result]
        assert "qc3" in ids

    def test_follows_blocked_by_edge(self, db_conn):
        create_node(db_conn, _node("qc4", node_type="task", title="T2"))
        create_node(db_conn, _node("qc5", node_type="blocker", title="Blocker2"))
        create_edge(db_conn, {"from": "qc4", "to": "qc5", "verb": "blocked by"})
        result = query_chain(db_conn, "qc4")
        ids = [r["dep.id"] for r in result]
        assert "qc5" in ids

    def test_chain_depth_is_set(self, db_conn):
        create_node(db_conn, _node("qc6", node_type="task", title="T3"))
        create_node(db_conn, _node("qc7", node_type="goal", title="G1"))
        create_edge(db_conn, {"from": "qc6", "to": "qc7", "verb": "depends on"})
        result = query_chain(db_conn, "qc6")
        assert result[0]["depth"] == 1

    def test_does_not_follow_non_dep_verb(self, db_conn):
        create_node(db_conn, _node("qc8", node_type="project", title="P"))
        create_node(db_conn, _node("qc9", node_type="person", title="Person"))
        create_edge(db_conn, {"from": "qc9", "to": "qc8", "verb": "works on"})
        result = query_chain(db_conn, "qc8")
        assert result == []


# ---------------------------------------------------------------------------
# get_stats
# ---------------------------------------------------------------------------

class TestGetStats:
    def test_empty_graph_returns_zero_counts(self, db_conn):
        stats = get_stats(db_conn)
        assert stats["total_nodes"] == 0
        assert stats["total_edges"] == 0

    def test_counts_nodes(self, db_conn):
        create_node(db_conn, _node("st1"))
        create_node(db_conn, _node("st2", node_type="person", title="P"))
        stats = get_stats(db_conn)
        assert stats["total_nodes"] == 2

    def test_counts_edges(self, db_conn):
        create_node(db_conn, _node("st3", node_type="project", title="P1"))
        create_node(db_conn, _node("st4", node_type="person", title="P2"))
        create_edge(db_conn, _edge("st4", "st3", "works on"))
        stats = get_stats(db_conn)
        assert stats["total_edges"] == 1

    def test_nodes_by_type_list_present(self, db_conn):
        create_node(db_conn, _node("st5"))
        stats = get_stats(db_conn)
        assert "nodes_by_type" in stats
        assert isinstance(stats["nodes_by_type"], list)

    def test_edges_by_verb_list_present(self, db_conn):
        create_node(db_conn, _node("st6", node_type="project", title="X"))
        create_node(db_conn, _node("st7", node_type="person", title="Y"))
        create_edge(db_conn, _edge("st7", "st6", "owns"))
        stats = get_stats(db_conn)
        assert "edges_by_verb" in stats
        verbs = [r["verb"] for r in stats["edges_by_verb"]]
        assert "owns" in verbs

    def test_nodes_with_embeddings_count(self, db_conn):
        stats = get_stats(db_conn)
        assert "nodes_with_embeddings" in stats
        assert isinstance(stats["nodes_with_embeddings"], int)
