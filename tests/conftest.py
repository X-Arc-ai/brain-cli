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
    set_brain_dir(brain_path)
    os.environ["BRAIN_PROJECT_ROOT"] = str(tmp_path)
    yield brain_path
    set_brain_dir(None)
    if "BRAIN_PROJECT_ROOT" in os.environ:
        del os.environ["BRAIN_PROJECT_ROOT"]


@pytest.fixture
def db_conn(brain_dir):
    """Create a test database connection with schema."""
    from brain_cli.database import get_connection
    from brain_cli.schema import create_schema
    conn = get_connection()
    create_schema(conn)
    yield conn
