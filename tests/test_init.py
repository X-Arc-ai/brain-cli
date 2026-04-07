"""Tests for brain_cli.init -- slugify, dir creation, project analysis."""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from brain_cli.init import _slugify, _step_1_create_dirs, _step_3_analyze_project


# ---------------------------------------------------------------------------
# _slugify
# ---------------------------------------------------------------------------

class TestSlugify:
    def test_lowercase(self):
        assert _slugify("Hello World") == "hello-world"

    def test_spaces_become_hyphens(self):
        assert _slugify("foo bar baz") == "foo-bar-baz"

    def test_special_chars_removed(self):
        assert _slugify("My Project (2024)!") == "my-project-2024"

    def test_consecutive_hyphens_collapsed(self):
        assert _slugify("a--b---c") == "a-b-c"

    def test_leading_trailing_hyphens_stripped(self):
        assert _slugify("--hello--") == "hello"

    def test_unicode_chars_stripped(self):
        result = _slugify("Anas Moujahid")
        assert result == "anas-moujahid"

    def test_max_length_50(self):
        long_title = "a" * 100
        assert len(_slugify(long_title)) <= 50

    def test_empty_string(self):
        assert _slugify("") == ""

    def test_only_special_chars(self):
        assert _slugify("!!!@@@###") == ""

    def test_numbers_preserved(self):
        assert _slugify("project-v2-alpha") == "project-v2-alpha"

    def test_underscores_become_hyphens(self):
        # Underscores survive the character class so they can be converted
        # to hyphens by the next pass.
        assert _slugify("my_project_name") == "my-project-name"
        assert _slugify("foo  bar") == "foo-bar"
        assert _slugify("Mixed_Case Name") == "mixed-case-name"


# ---------------------------------------------------------------------------
# _step_1_create_dirs
# ---------------------------------------------------------------------------

class TestStep1CreateDirs:
    def test_creates_brain_directory(self, brain_dir):
        # brain_dir fixture already creates it -- call step1 on a fresh path
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            fresh_brain = Path(td) / ".brain"
            from brain_cli.config import set_brain_dir
            set_brain_dir(fresh_brain)
            _step_1_create_dirs(fresh_brain)
            assert fresh_brain.exists()

    def test_creates_db_subdirectory(self, brain_dir):
        # Re-run step1 on the existing brain_dir (idempotent)
        _step_1_create_dirs(brain_dir)
        assert (brain_dir / "db").exists()

    def test_creates_exports_subdirectory(self, brain_dir):
        _step_1_create_dirs(brain_dir)
        assert (brain_dir / "exports").exists()

    def test_creates_config_json(self, brain_dir):
        # Remove config if it exists, then re-run
        config_path = brain_dir / "config.json"
        if config_path.exists():
            config_path.unlink()
        _step_1_create_dirs(brain_dir)
        assert config_path.exists()

    def test_config_json_is_valid(self, brain_dir):
        config_path = brain_dir / "config.json"
        if not config_path.exists():
            _step_1_create_dirs(brain_dir)
        data = json.loads(config_path.read_text())
        assert "type_tiers" in data
        assert "file_path_exceptions" in data

    def test_idempotent_second_call(self, brain_dir):
        # Should not raise on second call
        _step_1_create_dirs(brain_dir)
        _step_1_create_dirs(brain_dir)


# ---------------------------------------------------------------------------
# _step_3_analyze_project
# ---------------------------------------------------------------------------

class TestStep3AnalyzeProject:
    def test_detects_pyproject_toml(self, tmp_path, brain_dir):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "my-package"\n')
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr=""
            )
            proposals = _step_3_analyze_project(tmp_path)
        ids = [p["id"] for p in proposals if p.get("op") == "create_node"]
        # The slug of the directory name should appear as a project node
        assert len(ids) >= 1
        types = [p["type"] for p in proposals if p.get("op") == "create_node"]
        assert "project" in types

    def test_detects_readme_md(self, tmp_path, brain_dir):
        readme = tmp_path / "README.md"
        readme.write_text("# My Project\n")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr=""
            )
            proposals = _step_3_analyze_project(tmp_path)
        types = [p["type"] for p in proposals if p.get("op") == "create_node"]
        assert "project" in types

    def test_no_manifest_returns_empty(self, tmp_path, brain_dir):
        # Empty directory with no manifest files
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr=""
            )
            proposals = _step_3_analyze_project(tmp_path)
        assert proposals == []

    def test_git_authors_become_person_nodes(self, tmp_path, brain_dir):
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Alice\nBob\n",
                stderr="",
            )
            proposals = _step_3_analyze_project(tmp_path)
        person_nodes = [p for p in proposals
                        if p.get("op") == "create_node" and p.get("type") == "person"]
        person_titles = [p["title"] for p in person_nodes]
        assert "Alice" in person_titles
        assert "Bob" in person_titles

    def test_git_failure_gracefully_ignored(self, tmp_path, brain_dir):
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
            proposals = _step_3_analyze_project(tmp_path)
        # Should still have the project node
        project_nodes = [p for p in proposals
                         if p.get("op") == "create_node" and p.get("type") == "project"]
        assert len(project_nodes) >= 1

    def test_proposals_include_create_edges(self, tmp_path, brain_dir):
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Alice\n",
                stderr="",
            )
            proposals = _step_3_analyze_project(tmp_path)
        edges = [p for p in proposals if p.get("op") == "create_edge"]
        assert len(edges) >= 1

    def test_package_json_name_used_as_title(self, tmp_path, brain_dir):
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({"name": "my-js-package"}))
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr=""
            )
            proposals = _step_3_analyze_project(tmp_path)
        project_titles = [p["title"] for p in proposals
                          if p.get("op") == "create_node" and p.get("type") == "project"]
        assert "my-js-package" in project_titles
