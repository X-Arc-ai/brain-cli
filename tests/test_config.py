"""Tests for brain_cli.config -- paths, type system, constants."""

import os
import json
from pathlib import Path

import pytest

from brain_cli.config import (
    get_brain_dir,
    get_all_types,
    get_tier_for_type,
    get_immutable_types,
    get_runtime,
    VALID_STATUSES,
    set_brain_dir,
    DEFAULT_TYPE_TIERS,
)


# ---------------------------------------------------------------------------
# get_brain_dir resolution
# ---------------------------------------------------------------------------

class TestGetBrainDir:
    def test_override_takes_highest_priority(self, tmp_path):
        override = tmp_path / "override_brain"
        override.mkdir()
        set_brain_dir(override)
        try:
            assert get_brain_dir() == override
        finally:
            set_brain_dir(None)

    def test_env_var_used_when_no_override(self, tmp_path, monkeypatch):
        env_dir = tmp_path / "env_brain"
        env_dir.mkdir()
        monkeypatch.setenv("BRAIN_DIR", str(env_dir))
        set_brain_dir(None)
        assert get_brain_dir() == Path(str(env_dir))

    def test_local_dot_brain_used_when_exists(self, tmp_path, monkeypatch):
        set_brain_dir(None)
        monkeypatch.delenv("BRAIN_DIR", raising=False)
        local = tmp_path / ".brain"
        local.mkdir()
        monkeypatch.chdir(tmp_path)
        assert get_brain_dir() == local

    def test_fallback_to_home_dot_brain(self, monkeypatch):
        set_brain_dir(None)
        monkeypatch.delenv("BRAIN_DIR", raising=False)
        # Change to a directory that has no .brain subdir
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            monkeypatch.chdir(td)
            result = get_brain_dir()
        assert result == Path.home() / ".brain"


# ---------------------------------------------------------------------------
# Type system
# ---------------------------------------------------------------------------

class TestGetAllTypes:
    def test_returns_set(self, brain_dir):
        result = get_all_types()
        assert isinstance(result, set)

    def test_contains_default_types(self, brain_dir):
        result = get_all_types()
        # Structural tier
        assert "project" in result
        assert "person" in result
        # Operational tier
        assert "goal" in result
        assert "task" in result
        assert "decision" in result
        assert "blocker" in result
        # Temporal tier
        assert "event" in result
        assert "observation" in result
        assert "status_change" in result

    def test_user_types_merged_from_config(self, brain_dir):
        config_path = brain_dir / "config.json"
        config_path.write_text(json.dumps({
            "type_tiers": {"structural": ["company"]},
            "file_path_exceptions": [],
        }))
        result = get_all_types()
        assert "company" in result
        # Default types still present
        assert "project" in result


class TestGetTierForType:
    def test_known_structural_type(self, brain_dir):
        assert get_tier_for_type("project") == "structural"

    def test_known_operational_type(self, brain_dir):
        assert get_tier_for_type("goal") == "operational"

    def test_known_temporal_type(self, brain_dir):
        assert get_tier_for_type("event") == "temporal"

    def test_unknown_type_returns_none(self, brain_dir):
        assert get_tier_for_type("nonexistent_type") is None


class TestGetImmutableTypes:
    def test_returns_temporal_tier_types(self, brain_dir):
        immutable = get_immutable_types()
        temporal = DEFAULT_TYPE_TIERS["temporal"]
        assert immutable == temporal

    def test_returns_set(self, brain_dir):
        assert isinstance(get_immutable_types(), set)

    def test_event_is_immutable(self, brain_dir):
        assert "event" in get_immutable_types()

    def test_observation_is_immutable(self, brain_dir):
        assert "observation" in get_immutable_types()

    def test_project_is_not_immutable(self, brain_dir):
        assert "project" not in get_immutable_types()


# ---------------------------------------------------------------------------
# VALID_STATUSES
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# get_runtime
# ---------------------------------------------------------------------------

class TestGetRuntime:
    def test_default_when_no_config(self, brain_dir):
        config_path = brain_dir / "config.json"
        if config_path.exists():
            config_path.unlink()
        assert get_runtime() == "claude-code"

    def test_reads_runtime_from_config(self, brain_dir):
        config_path = brain_dir / "config.json"
        config_path.write_text(json.dumps({"runtime": "openclaw"}))
        assert get_runtime() == "openclaw"

    def test_default_when_field_missing(self, brain_dir):
        config_path = brain_dir / "config.json"
        config_path.write_text(json.dumps({"type_tiers": {}}))
        assert get_runtime() == "claude-code"

    def test_reads_headless(self, brain_dir):
        config_path = brain_dir / "config.json"
        config_path.write_text(json.dumps({"runtime": "headless"}))
        assert get_runtime() == "headless"


# ---------------------------------------------------------------------------
# VALID_STATUSES
# ---------------------------------------------------------------------------

class TestValidStatuses:
    def test_is_frozenset(self):
        assert isinstance(VALID_STATUSES, frozenset)

    def test_contains_expected_values(self):
        expected = {
            "active", "in_progress", "completed", "blocked",
            "stalled", "pending", "backlog", "archived", "cancelled",
        }
        assert expected == VALID_STATUSES
