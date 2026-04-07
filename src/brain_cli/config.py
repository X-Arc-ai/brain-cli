"""Brain CLI configuration -- paths, type system, constants.

All paths use LAZY RESOLUTION (functions, not module-level constants).
This is critical: brain init creates .brain/ AFTER config is imported.
If these were module-level constants, they'd resolve to ~/.brain/ before
.brain/ exists, and brain init would create the DB at the wrong location.
"""

import os
import json
from contextvars import ContextVar
from pathlib import Path
from datetime import datetime, timezone


# --- Path Resolution (LAZY) ---

_brain_dir_override: ContextVar[Path | None] = ContextVar(
    "brain_dir_override", default=None
)


def set_brain_dir(path: Path | None) -> None:
    """Override brain directory.

    Used by `brain init` to set a project-local path and by tests for
    isolation. Backed by a ContextVar so concurrent callers (e.g., tests
    running in parallel) don't stomp on each other.
    """
    _brain_dir_override.set(path)


def get_brain_dir() -> Path:
    """Resolve brain data directory.

    Priority:
    1. Explicit override (set by brain init or tests, via ContextVar)
    2. BRAIN_DIR env var
    3. .brain/ in current working directory (project-local)
    4. ~/.brain/ (global fallback)
    """
    override = _brain_dir_override.get()
    if override is not None:
        return override
    env = os.environ.get("BRAIN_DIR")
    if env:
        return Path(env)
    local = Path.cwd() / ".brain"
    if local.exists():
        return local
    return Path.home() / ".brain"


def get_db_path() -> Path:
    return get_brain_dir() / "db" / "brain.kuzu"


def get_export_dir() -> Path:
    return get_brain_dir() / "exports"


def get_project_root() -> Path:
    """Resolve project root for file_path resolution."""
    env = os.environ.get("BRAIN_PROJECT_ROOT")
    if env:
        return Path(env)
    return Path.cwd()


def get_data_dir() -> Path:
    """Get the package's bundled data directory."""
    return Path(__file__).parent / "data"


def get_viz_source_dir() -> Path:
    """Get the package's bundled viz files (source, for copying)."""
    return get_data_dir() / "viz"


# --- Type Tier System ---

DEFAULT_TYPE_TIERS = {
    "structural": {"project", "person"},
    "operational": {"goal", "task", "decision", "blocker"},
    "temporal": {"event", "observation", "status_change"},
}


def _load_user_tiers() -> dict[str, set[str]]:
    """Load user-defined type tiers from config file."""
    config_path = get_brain_dir() / "config.json"
    if not config_path.exists():
        return {}
    try:
        with open(config_path) as f:
            data = json.load(f)
        user_tiers = data.get("type_tiers", {})
        return {k: set(v) for k, v in user_tiers.items()}
    except (json.JSONDecodeError, KeyError, TypeError):
        return {}


def get_type_tiers() -> dict[str, set[str]]:
    """Get merged type tiers (defaults + user overrides)."""
    tiers = {k: set(v) for k, v in DEFAULT_TYPE_TIERS.items()}
    user = _load_user_tiers()
    for tier_name, types in user.items():
        if tier_name in tiers:
            tiers[tier_name] |= types
        else:
            tiers[tier_name] = set(types)
    return tiers


def get_all_types() -> set[str]:
    """Get all registered types across all tiers."""
    tiers = get_type_tiers()
    return set().union(*tiers.values()) if tiers else set()


def get_tier_for_type(node_type: str) -> str | None:
    """Get the tier for a given type, or None if unregistered."""
    tiers = get_type_tiers()
    for tier_name, types in tiers.items():
        if node_type in types:
            return tier_name
    return None


def get_immutable_types() -> set[str]:
    """Immutable types = temporal tier (cannot update after creation)."""
    tiers = get_type_tiers()
    return tiers.get("temporal", set())


# --- Statuses ---

VALID_STATUSES = frozenset({
    "active", "in_progress", "completed", "blocked",
    "stalled", "pending", "backlog", "archived", "cancelled",
})

# --- Staleness Thresholds (days) ---
STALENESS_HIGH = 7
STALENESS_MEDIUM = 14
STALENESS_LOW = 30

# --- Relationship Verb Constants ---
DECOMPOSITION_VERBS = ["has task", "decomposes into"]
DECOMPOSITION_VERBS_INVERSE = ["task of", "subtask of"]
BLOCKER_VERBS = ["blocked by", "depends on", "cannot start until"]

# --- Embedding Config ---
EMBEDDING_DIMS = 1536  # text-embedding-3-small

# --- Hygiene Config ---

# Types that MUST have file_path set
FILE_PATH_REQUIRED_TYPES = frozenset({"project", "person"})


def get_file_path_exceptions() -> set[str]:
    """Load node IDs exempt from file_path requirements."""
    config_path = get_brain_dir() / "config.json"
    if not config_path.exists():
        return set()
    try:
        with open(config_path) as f:
            return set(json.load(f).get("file_path_exceptions", []))
    except (json.JSONDecodeError, KeyError, TypeError):
        return set()


# --- Utility ---

def now():
    return datetime.now(timezone.utc)
