"""Kuzu database connection factory with retry on lock contention."""

import sys
import time
from contextlib import contextmanager

import kuzu

from .config import get_db_path
from .schema import create_schema

_cached_connection = None
_cached_db_path = None


def get_connection(max_retries=3, base_delay=2):
    """Get a Kuzu connection. Caches per-process for the same db_path.

    Schema is created once per connection lifecycle. Callers should not
    rely on a fresh connection per call -- use brain_connection() context
    manager for explicit lifetime management.

    Kuzu enforces single-writer via file lock. If another process holds
    the database open for writing, the Database() constructor fails
    immediately with RuntimeError. This retries with exponential backoff.
    """
    global _cached_connection, _cached_db_path
    db_path = get_db_path()

    if _cached_connection is not None and _cached_db_path == db_path:
        return _cached_connection

    db_path.parent.mkdir(parents=True, exist_ok=True)
    last_error = None
    for attempt in range(max_retries):
        try:
            db = kuzu.Database(str(db_path))
            conn = kuzu.Connection(db)
            create_schema(conn)
            _cached_connection = conn
            _cached_db_path = db_path
            return conn
        except RuntimeError as e:
            last_error = e
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(
                    f"[brain] DB lock contention (attempt {attempt + 1}/{max_retries}), "
                    f"retrying in {delay}s...",
                    file=sys.stderr,
                )
                time.sleep(delay)
    raise RuntimeError(f"Failed to open brain DB after {max_retries} attempts: {last_error}")


def reset_connection():
    """Drop the cached connection. Used by tests and after destructive ops."""
    global _cached_connection, _cached_db_path
    _cached_connection = None
    _cached_db_path = None


@contextmanager
def brain_connection(**kwargs):
    """Context manager for explicit connection lifetime.

    Within a single CLI invocation, this is effectively a no-op wrapper
    over the cached connection. The contextmanager exists so callers can
    use `with brain_connection() as conn:` instead of bare `del conn`.
    """
    conn = get_connection(**kwargs)
    try:
        yield conn
    finally:
        # Connection is process-cached; do not close.
        pass
