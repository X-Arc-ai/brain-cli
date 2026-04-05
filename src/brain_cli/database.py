"""Kuzu database connection factory with retry on lock contention."""

import sys
import time

import kuzu

from .config import get_db_path


def get_connection(max_retries=3, base_delay=2):
    """Get a Kuzu connection with retry on lock contention.

    Kuzu enforces single-writer via file lock. If another process holds
    the database open for writing, the Database() constructor fails
    immediately with RuntimeError. This retries with exponential backoff.
    """
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    last_error = None
    for attempt in range(max_retries):
        try:
            db = kuzu.Database(str(db_path))
            return kuzu.Connection(db)
        except RuntimeError as e:
            last_error = e
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"[brain] DB lock contention (attempt {attempt + 1}/{max_retries}), retrying in {delay}s...", file=sys.stderr)
                time.sleep(delay)
    raise RuntimeError(f"Failed to open brain DB after {max_retries} attempts: {last_error}")
