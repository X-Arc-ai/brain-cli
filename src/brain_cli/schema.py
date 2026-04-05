"""Database schema definition and migrations."""

from .config import EMBEDDING_DIMS

SCHEMA_VERSION = 2

NODE_TABLE = f"""
CREATE NODE TABLE IF NOT EXISTS Node (
    id STRING PRIMARY KEY,
    type STRING,
    title STRING,
    status STRING,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    verified_at TIMESTAMP,
    status_since TIMESTAMP,
    content STRING,
    file_path STRING,
    properties STRING,
    content_embedding FLOAT[{EMBEDDING_DIMS}]
)
"""

EDGE_TABLE = """
CREATE REL TABLE IF NOT EXISTS Edge (
    FROM Node TO Node,
    verb STRING,
    since TIMESTAMP,
    until TIMESTAMP,
    source STRING,
    note STRING,
    MANY_MANY
)
"""


def migrate_schema(conn):
    """Apply schema migrations. Idempotent -- safe to run multiple times."""
    try:
        result = conn.execute('CALL table_info("Node") RETURN *')
        cols = result.get_column_names()
        existing_columns = set()
        while result.has_next():
            row = dict(zip(cols, result.get_next()))
            existing_columns.add(row["name"])
    except Exception:
        return  # Table doesn't exist yet, create_schema will handle it

    if "content_embedding" not in existing_columns:
        conn.execute(f"ALTER TABLE Node ADD content_embedding FLOAT[{EMBEDDING_DIMS}]")


def create_schema(conn):
    """Create tables if they don't exist, then run migrations."""
    conn.execute(NODE_TABLE)
    conn.execute(EDGE_TABLE)
    migrate_schema(conn)
