import json
from datetime import datetime, timezone, timedelta

from .config import STALENESS_HIGH, STALENESS_MEDIUM, STALENESS_LOW
from .utils import rows_to_dicts


def _now():
    return datetime.now(timezone.utc)


def _to_aware(dt):
    """Ensure datetime is timezone-aware."""
    if dt is None:
        return None
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_recurring(row):
    """Parse recurring properties from a node row.

    Returns (is_recurring, frequency, last_completed) or (False, None, None).
    """
    props_str = row.get("n.properties") or ""
    if '"recurring": true' not in props_str and '"recurring":true' not in props_str:
        return False, None, None
    try:
        props = json.loads(props_str)
    except (json.JSONDecodeError, TypeError):
        return False, None, None
    return True, props.get("frequency"), props.get("last_completed")


# Map frequency to maximum allowed days since last_completed
_FREQUENCY_THRESHOLDS = {
    "daily": 1,
    "2x/week": 4,
    "weekly": 7,
    "biweekly": 14,
    "monthly": 31,
}


def compute_recurring_overdue(conn):
    """Find recurring activities that are overdue based on frequency vs last_completed."""
    result = conn.execute("""
        MATCH (n:Node)
        WHERE n.status IN ['active', 'in_progress', 'pending']
          AND n.properties IS NOT NULL
        RETURN n.id, n.type, n.title, n.status, n.properties
    """)
    rows = rows_to_dicts(result)
    now = _now()
    overdue = []
    for row in rows:
        is_recurring, frequency, last_completed = _parse_recurring(row)
        if not is_recurring:
            continue
        threshold = _FREQUENCY_THRESHOLDS.get(frequency)
        if threshold is None:
            continue
        if last_completed is None or last_completed == "never":
            overdue.append({
                "id": row["n.id"],
                "title": row["n.title"],
                "type": row["n.type"],
                "frequency": frequency,
                "last_completed": "never",
                "days_overdue": "never completed",
            })
            continue
        try:
            last_dt = datetime.strptime(last_completed, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        days_since = (now - last_dt).days
        if days_since > threshold:
            overdue.append({
                "id": row["n.id"],
                "title": row["n.title"],
                "type": row["n.type"],
                "frequency": frequency,
                "last_completed": last_completed,
                "days_overdue": days_since - threshold,
            })
    return overdue


def compute_staleness(conn):
    """Find nodes where freshness > threshold and status is active."""
    result = conn.execute("""
        MATCH (n:Node)
        WHERE n.status IN ['active', 'in_progress', 'pending', 'blocked']
          AND NOT n.type IN ['event', 'status_change', 'observation']
        RETURN n.id, n.type, n.title, n.status,
               n.updated_at, n.verified_at, n.properties
        ORDER BY n.updated_at ASC
    """)
    rows = rows_to_dicts(result)
    now = _now()
    stale = []
    for row in rows:
        is_recurring, _, _ = _parse_recurring(row)
        if is_recurring:
            continue
        updated = _to_aware(row.get("n.updated_at"))
        verified = _to_aware(row.get("n.verified_at"))
        last_touch = verified if (verified and updated and verified > updated) else updated
        if last_touch is None:
            continue
        days = (now - last_touch).days
        if days >= STALENESS_HIGH:
            level = "CRITICAL" if days >= STALENESS_LOW else ("WARNING" if days >= STALENESS_MEDIUM else "INFO")
            stale.append({
                "id": row["n.id"],
                "title": row["n.title"],
                "type": row["n.type"],
                "status": row["n.status"],
                "days_stale": days,
                "level": level,
            })
    return stale


def compute_dependency_freshness(conn):
    """Find dependencies where target changed after source was last verified."""
    result = conn.execute("""
        MATCH (source:Node)-[e:Edge]->(target:Node)
        WHERE e.verb IN ['depends on', 'cannot start until', 'blocked by', 'requires']
          AND e.until IS NULL
          AND source.verified_at IS NOT NULL
          AND target.updated_at > source.verified_at
        RETURN source.id, source.title, target.id, target.title,
               source.verified_at, target.updated_at, e.verb
    """)
    rows = rows_to_dicts(result)
    alerts = []
    for row in rows:
        alerts.append({
            "source": row["source.id"],
            "source_title": row["source.title"],
            "target": row["target.id"],
            "target_title": row["target.title"],
            "verb": row["e.verb"],
            "source_verified": str(row["source.verified_at"]),
            "target_updated": str(row["target.updated_at"]),
        })
    return alerts


def compute_velocity_zero(conn):
    """Find operational items stuck in any non-terminal status too long.

    "verified_at" means "I looked and it's still accurate" -- that is NOT progress.
    Only status_since (when status last changed) determines velocity.

    Thresholds:
    - blocked/stalled: 7 days (should be actively resolved)
    - in_progress/pending/active: 14 days (should show movement)
    """
    result = conn.execute("""
        MATCH (n:Node)
        WHERE n.status IN ['in_progress', 'blocked', 'stalled', 'pending', 'active']
          AND n.type IN ['task', 'goal', 'blocker']
        RETURN n.id, n.title, n.type, n.status, n.status_since, n.created_at, n.properties
        ORDER BY n.status_since ASC
    """)
    rows = rows_to_dicts(result)
    now = _now()
    stalled = []
    for row in rows:
        is_recurring, _, _ = _parse_recurring(row)
        if is_recurring:
            continue
        since = _to_aware(row.get("n.status_since"))
        if since is None:
            # Fallback: use created_at if status_since was never set
            # (nodes created before status_since was added to schema)
            created_at = _to_aware(row.get("n.created_at"))
            if created_at is None:
                continue
            since = created_at
        days = (now - since).days
        # Blocked/stalled items should resolve faster
        threshold = 7 if row["n.status"] in ("blocked", "stalled") else 14
        if days >= threshold:
            stalled.append({
                "id": row["n.id"],
                "title": row["n.title"],
                "type": row.get("n.type"),
                "status": row["n.status"],
                "days_stuck": days,
            })
    return stalled


def compute_recently_completed(conn):
    """Find items completed in the last 7 days -- potential unblockers."""
    cutoff = _now() - timedelta(days=7)
    result = conn.execute("""
        MATCH (n:Node)
        WHERE n.status = 'completed'
          AND n.status_since IS NOT NULL
          AND n.status_since > timestamp($cutoff)
        RETURN n.id, n.title, n.type, n.status_since
        ORDER BY n.status_since DESC
    """, parameters={"cutoff": cutoff.strftime("%Y-%m-%d %H:%M:%S")})
    rows = rows_to_dicts(result)
    return [
        {
            "id": row["n.id"],
            "title": row["n.title"],
            "type": row["n.type"],
            "completed": str(row["n.status_since"]),
        }
        for row in rows
    ]


def compute_all_signals(conn):
    """Compute all signal types and return combined output."""
    stale = compute_staleness(conn)
    dep_changed = compute_dependency_freshness(conn)
    velocity = compute_velocity_zero(conn)
    completed = compute_recently_completed(conn)
    recurring = compute_recurring_overdue(conn)

    return {
        "generated_at": _now().isoformat(),
        "signals": {
            "stale": stale,
            "dependency_changed": dep_changed,
            "velocity_zero": velocity,
            "recently_completed": completed,
            "recurring_overdue": recurring,
        },
        "summary": {
            "stale_critical": sum(1 for s in stale if s["level"] == "CRITICAL"),
            "stale_warning": sum(1 for s in stale if s["level"] == "WARNING"),
            "stale_info": sum(1 for s in stale if s["level"] == "INFO"),
            "dependency_alerts": len(dep_changed),
            "velocity_zero": len(velocity),
            "recently_completed": len(completed),
            "recurring_overdue": len(recurring),
        },
    }
