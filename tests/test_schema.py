"""Tests for brain_cli.schema -- idempotency and migrations."""

import pytest

from brain_cli.schema import create_schema, migrate_schema, SCHEMA_VERSION
from brain_cli.utils import rows_to_dicts


class TestCreateSchema:
    def test_creates_node_table(self, db_conn):
        # If table doesn't exist, execute should raise. Querying it confirms creation.
        result = db_conn.execute("MATCH (n:Node) RETURN count(*) AS cnt")
        rows = rows_to_dicts(result)
        assert rows[0]["cnt"] == 0

    def test_creates_edge_table(self, db_conn):
        result = db_conn.execute("MATCH ()-[e:Edge]->() RETURN count(*) AS cnt")
        rows = rows_to_dicts(result)
        assert rows[0]["cnt"] == 0

    def test_idempotent_first_call(self, db_conn):
        # db_conn already called create_schema once via fixture; call it again
        create_schema(db_conn)

    def test_idempotent_second_call(self, db_conn):
        create_schema(db_conn)
        create_schema(db_conn)
        # No exception means idempotent

    def test_node_table_has_id_column(self, db_conn):
        result = db_conn.execute('CALL table_info("Node") RETURN *')
        cols = result.get_column_names()
        column_names = set()
        while result.has_next():
            row = dict(zip(cols, result.get_next()))
            column_names.add(row["name"])
        assert "id" in column_names

    def test_node_table_has_content_embedding_column(self, db_conn):
        result = db_conn.execute('CALL table_info("Node") RETURN *')
        cols = result.get_column_names()
        column_names = set()
        while result.has_next():
            row = dict(zip(cols, result.get_next()))
            column_names.add(row["name"])
        assert "content_embedding" in column_names


class TestMigrateSchema:
    def test_migrate_on_existing_db_no_error(self, db_conn):
        # Already migrated (content_embedding exists), second migrate is safe
        migrate_schema(db_conn)

    def test_migrate_on_empty_connection_returns_safely(self, brain_dir):
        # A fresh connection where no tables exist yet
        from brain_cli.database import get_connection
        conn = get_connection()
        # Should return without error (table doesn't exist branch)
        migrate_schema(conn)
