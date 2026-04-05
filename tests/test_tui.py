"""Tests for brain_cli.tui -- Rich formatting functions don't crash."""

from io import StringIO

import pytest
from rich.console import Console


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_console():
    """Create an in-memory Rich console for capturing output."""
    return Console(file=StringIO(), highlight=False, markup=True)


def _render(fn, *args, **kwargs):
    """Invoke a tui function with an in-memory console, return captured text."""
    console = _make_console()
    # Patch the module-level console in tui
    import brain_cli.tui as tui_mod
    original = tui_mod.console
    tui_mod.console = console
    try:
        fn(*args, **kwargs)
    finally:
        tui_mod.console = original
    return console.file.getvalue()


# ---------------------------------------------------------------------------
# Minimal mock data builders
# ---------------------------------------------------------------------------

def _scan_data(node_id="root", title="Root Node", node_type="project",
               status="active", hop1_count=0):
    nodes_by_hop = {}
    if hop1_count > 0:
        nodes_by_hop[1] = [
            {
                "id": f"child-{i}",
                "type": "person",
                "title": f"Child {i}",
                "status": "active",
                "file_path": None,
            }
            for i in range(hop1_count)
        ]
    return {
        "root": {
            "id": node_id,
            "title": title,
            "type": node_type,
            "status": status,
            "content": "Root content",
            "file_path": None,
            "properties": None,
        },
        "scan_depth": 3,
        "total_nodes": 1 + hop1_count,
        "nodes_by_hop": nodes_by_hop,
        "edges": [],
    }


def _signals_data(stale=None, velocity=None, completed=None):
    stale = stale or []
    velocity = velocity or []
    completed = completed or []
    return {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "signals": {
            "stale": stale,
            "dependency_changed": [],
            "velocity_zero": velocity,
            "recently_completed": completed,
            "recurring_overdue": [],
        },
        "summary": {
            "stale_critical": sum(1 for s in stale if s.get("level") == "CRITICAL"),
            "stale_warning": sum(1 for s in stale if s.get("level") == "WARNING"),
            "stale_info": sum(1 for s in stale if s.get("level") == "INFO"),
            "dependency_alerts": 0,
            "velocity_zero": len(velocity),
            "recently_completed": len(completed),
            "recurring_overdue": 0,
        },
    }


def _node_data(node_id="n1", title="A Node", node_type="project",
               status="active", edges_out=None, edges_in=None):
    return {
        "id": node_id,
        "title": title,
        "type": node_type,
        "status": status,
        "content": "Some content about this node",
        "file_path": "context/test.md",
        "properties": None,
        "edges_out": edges_out or [],
        "edges_in": edges_in or [],
    }


def _stats_data(node_count=5, edge_count=3):
    return {
        "total_nodes": node_count,
        "total_edges": edge_count,
        "nodes_with_embeddings": 0,
        "nodes_by_type": [
            {"type": "project", "count": 2},
            {"type": "person", "count": 3},
        ],
        "edges_by_verb": [
            {"verb": "works on", "count": 2},
            {"verb": "manages", "count": 1},
        ],
    }


# ---------------------------------------------------------------------------
# format_scan
# ---------------------------------------------------------------------------

class TestFormatScan:
    def test_does_not_raise_empty_hops(self):
        from brain_cli.tui import format_scan
        _render(format_scan, _scan_data())

    def test_does_not_raise_with_hop1_nodes(self):
        from brain_cli.tui import format_scan
        _render(format_scan, _scan_data(hop1_count=3))

    def test_output_contains_root_title(self):
        from brain_cli.tui import format_scan
        output = _render(format_scan, _scan_data(title="My Root"))
        assert "My Root" in output

    def test_output_contains_total_count(self):
        from brain_cli.tui import format_scan
        data = _scan_data(hop1_count=2)
        output = _render(format_scan, data)
        assert "3" in output  # 1 root + 2 children

    def test_output_contains_status(self):
        from brain_cli.tui import format_scan
        output = _render(format_scan, _scan_data(status="blocked"))
        assert "blocked" in output


# ---------------------------------------------------------------------------
# format_signals
# ---------------------------------------------------------------------------

class TestFormatSignals:
    def test_does_not_raise_empty(self):
        from brain_cli.tui import format_signals
        _render(format_signals, _signals_data())

    def test_empty_signals_shows_no_active_signals(self):
        from brain_cli.tui import format_signals
        output = _render(format_signals, _signals_data())
        assert "No active signals" in output

    def test_stale_signal_shown_in_table(self):
        from brain_cli.tui import format_signals
        stale = [{"id": "old-node", "title": "Old Node", "type": "goal",
                  "status": "active", "days_stale": 30, "level": "CRITICAL"}]
        output = _render(format_signals, _signals_data(stale=stale))
        assert "old-node" in output

    def test_velocity_zero_signal_shown(self):
        from brain_cli.tui import format_signals
        velocity = [{"id": "stuck-task", "title": "Stuck Task", "type": "task",
                     "status": "in_progress", "days_stuck": 16}]
        output = _render(format_signals, _signals_data(velocity=velocity))
        assert "stuck-task" in output

    def test_summary_shown_when_nonzero(self):
        from brain_cli.tui import format_signals
        stale = [{"id": "x", "title": "X", "type": "goal", "days_stale": 30,
                  "level": "CRITICAL"}]
        output = _render(format_signals, _signals_data(stale=stale))
        # Summary line should contain counts
        assert "stale_critical: 1" in output


# ---------------------------------------------------------------------------
# format_node
# ---------------------------------------------------------------------------

class TestFormatNode:
    def test_does_not_raise(self):
        from brain_cli.tui import format_node
        _render(format_node, _node_data())

    def test_output_contains_title(self):
        from brain_cli.tui import format_node
        output = _render(format_node, _node_data(title="Special Node"))
        assert "Special Node" in output

    def test_output_contains_type(self):
        from brain_cli.tui import format_node
        output = _render(format_node, _node_data(node_type="person"))
        assert "person" in output

    def test_output_contains_status(self):
        from brain_cli.tui import format_node
        output = _render(format_node, _node_data(status="blocked"))
        assert "blocked" in output

    def test_output_contains_content(self):
        from brain_cli.tui import format_node
        output = _render(format_node, _node_data())
        assert "Some content" in output

    def test_outgoing_edges_shown(self):
        from brain_cli.tui import format_node
        edges_out = [{"e.verb": "works on", "target_id": "proj-1",
                      "target_title": "Project 1", "target_type": "project",
                      "e.since": None, "e.until": None, "e.source": None, "e.note": None}]
        output = _render(format_node, _node_data(edges_out=edges_out))
        assert "works on" in output

    def test_incoming_edges_shown(self):
        from brain_cli.tui import format_node
        edges_in = [{"e.verb": "manages", "source_id": "manager-1",
                     "source_title": "Manager", "source_type": "person",
                     "e.since": None, "e.until": None, "e.source": None, "e.note": None}]
        output = _render(format_node, _node_data(edges_in=edges_in))
        assert "manages" in output

    def test_file_path_shown(self):
        from brain_cli.tui import format_node
        output = _render(format_node, _node_data())
        assert "context/test.md" in output

    def test_does_not_raise_with_no_content(self):
        from brain_cli.tui import format_node
        data = _node_data()
        data["content"] = None
        data["file_path"] = None
        _render(format_node, data)


# ---------------------------------------------------------------------------
# format_stats
# ---------------------------------------------------------------------------

class TestFormatStats:
    def test_does_not_raise(self):
        from brain_cli.tui import format_stats
        _render(format_stats, _stats_data())

    def test_output_contains_total_nodes(self):
        from brain_cli.tui import format_stats
        output = _render(format_stats, _stats_data(node_count=7))
        assert "7" in output

    def test_output_contains_total_edges(self):
        from brain_cli.tui import format_stats
        output = _render(format_stats, _stats_data(edge_count=4))
        assert "4" in output

    def test_output_contains_type_names(self):
        from brain_cli.tui import format_stats
        output = _render(format_stats, _stats_data())
        assert "project" in output
        assert "person" in output

    def test_empty_stats_does_not_raise(self):
        from brain_cli.tui import format_stats
        _render(format_stats, {
            "total_nodes": 0,
            "total_edges": 0,
            "nodes_with_embeddings": 0,
            "nodes_by_type": [],
            "edges_by_verb": [],
        })
