"""Tests for brain_cli.dream -- multi-session dream orchestrator."""

import json
import subprocess

import pytest
from unittest.mock import patch, MagicMock

from brain_cli.dream import (
    run_phased_dream,
    _load_protected_nodes,
    _build_phase_prompt,
    _run_agent_session,
    _write_state,
    _write_report,
)


# ---------------------------------------------------------------------------
# _load_protected_nodes
# ---------------------------------------------------------------------------

class TestLoadProtectedNodes:
    def test_empty_default_when_no_file(self, brain_dir):
        result = _load_protected_nodes(brain_dir)
        assert result == []

    def test_loads_from_file(self, brain_dir):
        path = brain_dir / "protected-nodes.json"
        path.write_text(json.dumps(["node-a", "node-b"]))
        result = _load_protected_nodes(brain_dir)
        assert result == ["node-a", "node-b"]

    def test_empty_array_file(self, brain_dir):
        path = brain_dir / "protected-nodes.json"
        path.write_text("[]")
        result = _load_protected_nodes(brain_dir)
        assert result == []


# ---------------------------------------------------------------------------
# _build_phase_prompt
# ---------------------------------------------------------------------------

class TestBuildPhasePrompt:
    def test_includes_preamble(self, tmp_path):
        phase_file = tmp_path / "phase1.md"
        phase_file.write_text("# Phase 1 content")
        state = {"protected_nodes": [], "phase_results": {}}
        result = _build_phase_prompt("PREAMBLE TEXT", phase_file, state, 1)
        assert "PREAMBLE TEXT" in result
        assert "Phase 1 content" in result

    def test_includes_state_json(self, tmp_path):
        phase_file = tmp_path / "phase2.md"
        phase_file.write_text("# Phase 2")
        state = {"protected_nodes": ["abc"], "phase_results": {"phase1": {"status": "ok"}}}
        result = _build_phase_prompt("", phase_file, state, 2)
        assert '"protected_nodes"' in result
        assert '"abc"' in result

    def test_includes_phase_content(self, tmp_path):
        phase_file = tmp_path / "test_phase.md"
        phase_file.write_text("Run hygiene checks")
        result = _build_phase_prompt("", phase_file, {}, 1)
        assert "Run hygiene checks" in result


# ---------------------------------------------------------------------------
# _write_state / _write_report
# ---------------------------------------------------------------------------

class TestWriteState:
    def test_creates_state_file(self, brain_dir):
        state = {"phase_results": {"phase1": "ok"}}
        _write_state(brain_dir, state)
        path = brain_dir / ".dream-state.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["phase_results"]["phase1"] == "ok"


class TestWriteReport:
    def test_creates_report_file(self, brain_dir):
        state = {"phase_results": {"phase1": "ok", "phase2": "done"}}
        _write_report(brain_dir, state)
        path = brain_dir / "last-dream-report.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert len(data["phase_results"]) == 2


# ---------------------------------------------------------------------------
# _run_agent_session
# ---------------------------------------------------------------------------

class TestRunAgentSession:
    def test_handles_timeout(self):
        with patch("brain_cli.dream.subprocess.run",
                   side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=600)):
            result = _run_agent_session("test prompt")
        assert result["status"] == "timeout"

    def test_handles_missing_claude(self):
        with patch("brain_cli.dream.subprocess.run",
                   side_effect=FileNotFoundError("claude not found")):
            result = _run_agent_session("test prompt")
        assert result["status"] == "error"
        assert "not found" in result["stderr"]

    def test_parses_json_output(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"status": "ok", "findings": []}'
        with patch("brain_cli.dream.subprocess.run", return_value=mock_result):
            result = _run_agent_session("test prompt")
        assert result["status"] == "ok"

    def test_handles_non_json_output(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Plain text output from agent"
        with patch("brain_cli.dream.subprocess.run", return_value=mock_result):
            result = _run_agent_session("test prompt")
        assert result["status"] == "completed"
        assert "Plain text" in result["output"]

    def test_handles_error_returncode(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Something went wrong"
        with patch("brain_cli.dream.subprocess.run", return_value=mock_result):
            result = _run_agent_session("test prompt")
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# run_phased_dream
# ---------------------------------------------------------------------------

class TestRunPhasedDream:
    def test_dry_run_no_subprocess_calls(self, brain_dir):
        with patch("brain_cli.dream.get_runtime", return_value="claude-code"):
            result = run_phased_dream(dry_run=True)
        phases = result.get("phase_results", {})
        assert len(phases) > 0
        for name, phase_result in phases.items():
            assert phase_result["status"] == "dry-run"

    def test_non_claude_code_runtime_raises(self, brain_dir):
        with patch("brain_cli.dream.get_runtime", return_value="openclaw"):
            with pytest.raises(RuntimeError, match="Phased dream requires claude-code"):
                run_phased_dream()

    def test_headless_runtime_raises(self, brain_dir):
        with patch("brain_cli.dream.get_runtime", return_value="headless"):
            with pytest.raises(RuntimeError, match="Phased dream requires claude-code"):
                run_phased_dream()

    def test_writes_report_on_dry_run(self, brain_dir):
        with patch("brain_cli.dream.get_runtime", return_value="claude-code"):
            run_phased_dream(dry_run=True)
        report = brain_dir / "last-dream-report.json"
        assert report.exists()
