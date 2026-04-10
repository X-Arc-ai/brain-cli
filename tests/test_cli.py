"""Tests for brain_cli.cli -- Click commands via CliRunner."""

import json
import os

import pytest
from click.testing import CliRunner

from brain_cli.cli import cli


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _runner_with_brain(brain_dir):
    """Return a CliRunner with env pointing to the test brain directory."""
    runner = CliRunner()
    env = {
        "BRAIN_DIR": str(brain_dir),
        "BRAIN_PROJECT_ROOT": str(brain_dir.parent),
    }
    return runner, env


def _create_node_via_cli(runner, env, node_id, node_type="project", title=None):
    """Helper to create a node through the CLI."""
    data = {"id": node_id, "type": node_type, "title": title or node_id}
    result = runner.invoke(
        cli,
        ["write", "node", "--json-data", json.dumps(data)],
        env=env,
    )
    return result


# ---------------------------------------------------------------------------
# Meta commands
# ---------------------------------------------------------------------------

class TestCliMeta:
    def test_version(self):
        from brain_cli import __version__
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "brain" in result.output.lower()


class TestQueryCypherSafety:
    def test_read_only_rejects_delete(self, brain_dir):
        runner, env = _runner_with_brain(brain_dir)
        result = runner.invoke(
            cli,
            ["query", "cypher", "MATCH (n:Node) DETACH DELETE n", "--read-only"],
            env=env,
        )
        assert result.exit_code == 2
        assert "destructive" in result.output.lower()

    def test_read_only_allows_match(self, brain_dir):
        runner, env = _runner_with_brain(brain_dir)
        result = runner.invoke(
            cli,
            ["query", "cypher", "MATCH (n:Node) RETURN count(n)", "--read-only"],
            env=env,
        )
        assert result.exit_code == 0

    def test_help_warns_about_destructive(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["query", "cypher", "--help"])
        assert "WARNING" in result.output
        assert "delete data" in result.output.lower() or "modify" in result.output.lower()


# ---------------------------------------------------------------------------
# scan command
# ---------------------------------------------------------------------------

class TestScanCommand:
    def test_scan_existing_node_exits_0(self, brain_dir):
        runner, env = _runner_with_brain(brain_dir)
        _create_node_via_cli(runner, env, "scan_node1", title="Scan Me")
        result = runner.invoke(cli, ["scan", "scan_node1"], env=env)
        assert result.exit_code == 0

    def test_scan_nonexistent_node_exits_1(self, brain_dir):
        runner, env = _runner_with_brain(brain_dir)
        result = runner.invoke(cli, ["scan", "ghost_node"], env=env)
        assert result.exit_code == 1

    def test_scan_json_mode_returns_parseable_output(self, brain_dir):
        runner, env = _runner_with_brain(brain_dir)
        _create_node_via_cli(runner, env, "scan_json1", title="JSON Scan")
        result = runner.invoke(
            cli, ["--json-output", "scan", "scan_json1"], env=env
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["root"]["id"] == "scan_json1"


# ---------------------------------------------------------------------------
# write node command
# ---------------------------------------------------------------------------

class TestWriteNodeCommand:
    def test_write_creates_node(self, brain_dir):
        runner, env = _runner_with_brain(brain_dir)
        data = {"id": "wn1", "type": "project", "title": "Write Node Test"}
        result = runner.invoke(
            cli, ["write", "node", "--json-data", json.dumps(data)], env=env
        )
        assert result.exit_code == 0
        assert "wn1" in result.output

    def test_write_node_missing_field_exits_nonzero(self, brain_dir):
        runner, env = _runner_with_brain(brain_dir)
        data = {"type": "project", "title": "Missing ID"}
        result = runner.invoke(
            cli, ["write", "node", "--json-data", json.dumps(data)], env=env
        )
        assert result.exit_code != 0

    def test_write_node_update_op(self, brain_dir):
        runner, env = _runner_with_brain(brain_dir)
        # Create first
        _create_node_via_cli(runner, env, "wn2", title="Original")
        # Update
        update_data = {"op": "update_node", "id": "wn2", "title": "Updated"}
        result = runner.invoke(
            cli, ["write", "node", "--json-data", json.dumps(update_data)], env=env
        )
        assert result.exit_code == 0
        assert "Updated" in result.output or "wn2" in result.output


# ---------------------------------------------------------------------------
# signals command
# ---------------------------------------------------------------------------

class TestSignalsCommand:
    def test_signals_exits_0(self, brain_dir):
        runner, env = _runner_with_brain(brain_dir)
        result = runner.invoke(cli, ["signals"], env=env)
        assert result.exit_code == 0

    def test_signals_json_mode_parseable(self, brain_dir):
        runner, env = _runner_with_brain(brain_dir)
        result = runner.invoke(cli, ["--json-output", "signals"], env=env)
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "signals" in parsed
        assert "summary" in parsed


# ---------------------------------------------------------------------------
# stats command
# ---------------------------------------------------------------------------

class TestStatsCommand:
    def test_stats_exits_0(self, brain_dir):
        runner, env = _runner_with_brain(brain_dir)
        result = runner.invoke(cli, ["stats"], env=env)
        assert result.exit_code == 0

    def test_stats_json_mode_parseable(self, brain_dir):
        runner, env = _runner_with_brain(brain_dir)
        result = runner.invoke(cli, ["--json-output", "stats"], env=env)
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "total_nodes" in parsed
        assert "total_edges" in parsed

    def test_stats_counts_created_nodes(self, brain_dir):
        runner, env = _runner_with_brain(brain_dir)
        _create_node_via_cli(runner, env, "stats_n1", title="N1")
        _create_node_via_cli(runner, env, "stats_n2", node_type="person", title="N2")
        result = runner.invoke(cli, ["--json-output", "stats"], env=env)
        parsed = json.loads(result.output)
        assert parsed["total_nodes"] >= 2


# ---------------------------------------------------------------------------
# config show command
# ---------------------------------------------------------------------------

class TestConfigShowCommand:
    def test_config_show_exits_0(self, brain_dir):
        runner, env = _runner_with_brain(brain_dir)
        result = runner.invoke(cli, ["config", "show"], env=env)
        assert result.exit_code == 0

    def test_config_show_includes_brain_dir(self, brain_dir):
        runner, env = _runner_with_brain(brain_dir)
        result = runner.invoke(cli, ["config", "show"], env=env)
        assert str(brain_dir) in result.output

    def test_config_show_lists_type_tiers(self, brain_dir):
        runner, env = _runner_with_brain(brain_dir)
        result = runner.invoke(cli, ["config", "show"], env=env)
        assert "structural" in result.output
        assert "operational" in result.output
        assert "temporal" in result.output


# ---------------------------------------------------------------------------
# verify command
# ---------------------------------------------------------------------------

class TestVerifyCommand:
    def test_verify_existing_node_exits_0(self, brain_dir):
        runner, env = _runner_with_brain(brain_dir)
        _create_node_via_cli(runner, env, "ver1", title="Verify Me")
        result = runner.invoke(cli, ["verify", "ver1"], env=env)
        assert result.exit_code == 0
        assert "ver1" in result.output

    def test_verify_nonexistent_node_exits_0(self, brain_dir):
        # brain verify on a missing node does a MATCH + SET which is a no-op
        runner, env = _runner_with_brain(brain_dir)
        result = runner.invoke(cli, ["verify", "ghost_ver"], env=env)
        assert result.exit_code == 0

    def test_verify_stale_flag_lists_stale_nodes(self, brain_dir):
        runner, env = _runner_with_brain(brain_dir)
        result = runner.invoke(cli, ["verify", "--stale", "14"], env=env)
        assert result.exit_code == 0

    def test_verify_no_args_exits_1(self, brain_dir):
        runner, env = _runner_with_brain(brain_dir)
        result = runner.invoke(cli, ["verify"], env=env)
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# write batch command
# ---------------------------------------------------------------------------

class TestWriteBatchCommand:
    def test_write_batch_creates_nodes(self, brain_dir):
        runner, env = _runner_with_brain(brain_dir)
        ops = [
            {"op": "create_node", "id": "batch_cli1", "type": "project", "title": "Batch 1"},
            {"op": "create_node", "id": "batch_cli2", "type": "person", "title": "Batch 2"},
        ]
        result = runner.invoke(
            cli, ["write", "batch", "--json-data", json.dumps(ops)], env=env
        )
        assert result.exit_code == 0

    def test_write_batch_output_is_json(self, brain_dir):
        runner, env = _runner_with_brain(brain_dir)
        ops = [{"op": "create_node", "id": "batch_cli3", "type": "project", "title": "T"}]
        result = runner.invoke(
            cli, ["write", "batch", "--json-data", json.dumps(ops)], env=env
        )
        assert result.exit_code == 0
        assert "Batch complete" in result.output
        # JSON array is present somewhere in the output
        assert '"summary"' in result.output


# ---------------------------------------------------------------------------
# get command
# ---------------------------------------------------------------------------

class TestGetCommand:
    def test_get_existing_node_exits_0(self, brain_dir):
        runner, env = _runner_with_brain(brain_dir)
        _create_node_via_cli(runner, env, "get_n1", title="Get Me")
        result = runner.invoke(cli, ["get", "get_n1"], env=env)
        assert result.exit_code == 0

    def test_get_missing_node_exits_1(self, brain_dir):
        runner, env = _runner_with_brain(brain_dir)
        result = runner.invoke(cli, ["get", "missing_node"], env=env)
        assert result.exit_code == 1

    def test_get_json_mode_returns_node_data(self, brain_dir):
        runner, env = _runner_with_brain(brain_dir)
        _create_node_via_cli(runner, env, "get_n2", title="JSON Get")
        result = runner.invoke(cli, ["--json-output", "get", "get_n2"], env=env)
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["id"] == "get_n2"


# ---------------------------------------------------------------------------
# init --runtime / --headless
# ---------------------------------------------------------------------------

class TestInitRuntimeFlag:
    def test_headless_flag_sets_runtime(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(cli, ["init", "--headless", "--project", str(tmp_path)])
        assert result.exit_code == 0
        config = json.loads((tmp_path / ".brain" / "config.json").read_text())
        assert config["runtime"] == "headless"

    def test_headless_skips_claude_artifacts(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(cli, ["init", "--headless", "--project", str(tmp_path)])
        assert result.exit_code == 0
        assert not (tmp_path / "CLAUDE.md").exists()
        assert not (tmp_path / ".claude").exists()

    def test_runtime_openclaw_skips_claude_artifacts(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "init", "--runtime", "openclaw", "--yes",
            "--skip-memory", "--skip-viz",
            "--project", str(tmp_path),
        ])
        assert result.exit_code == 0
        assert not (tmp_path / "CLAUDE.md").exists()
        assert not (tmp_path / ".claude").exists()
        config = json.loads((tmp_path / ".brain" / "config.json").read_text())
        assert config["runtime"] == "openclaw"

    def test_no_flags_preserves_claude_code_default(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "init", "--yes", "--skip-viz", "--skip-memory",
            "--project", str(tmp_path),
        ])
        assert result.exit_code == 0
        config = json.loads((tmp_path / ".brain" / "config.json").read_text())
        assert config["runtime"] == "claude-code"

    def test_skip_hooks_overrides_runtime(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "init", "--runtime", "openclaw", "--skip-hooks", "--yes",
            "--skip-memory", "--skip-viz",
            "--project", str(tmp_path),
        ])
        assert result.exit_code == 0
        # runtime is stored but no skills installed
        config = json.loads((tmp_path / ".brain" / "config.json").read_text())
        assert config["runtime"] == "openclaw"
        assert not (tmp_path / "CLAUDE.md").exists()
