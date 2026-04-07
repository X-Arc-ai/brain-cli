import pytest
import os
from pathlib import Path


@pytest.fixture
def brain_dir(tmp_path):
    """Create a temporary brain directory for tests."""
    brain_path = tmp_path / ".brain"
    brain_path.mkdir()
    (brain_path / "db").mkdir()
    (brain_path / "exports").mkdir()
    from brain_cli.config import set_brain_dir
    from brain_cli.database import reset_connection
    set_brain_dir(brain_path)
    reset_connection()

    saved_brain_dir = os.environ.pop("BRAIN_DIR", None)
    saved_project_root = os.environ.pop("BRAIN_PROJECT_ROOT", None)
    os.environ["BRAIN_PROJECT_ROOT"] = str(tmp_path)

    yield brain_path

    set_brain_dir(None)
    reset_connection()
    os.environ.pop("BRAIN_DIR", None)
    os.environ.pop("BRAIN_PROJECT_ROOT", None)
    if saved_brain_dir is not None:
        os.environ["BRAIN_DIR"] = saved_brain_dir
    if saved_project_root is not None:
        os.environ["BRAIN_PROJECT_ROOT"] = saved_project_root


@pytest.fixture
def db_conn(brain_dir):
    """Create a test database connection with schema."""
    from brain_cli.database import get_connection
    conn = get_connection()
    yield conn
