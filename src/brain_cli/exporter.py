import json
from datetime import datetime, timezone

from .config import get_export_dir, STALENESS_HIGH, STALENESS_MEDIUM, STALENESS_LOW
from .utils import rows_to_dicts


def _staleness_level(updated_at, verified_at):
    """Compute staleness level for a node."""
    now = datetime.now(timezone.utc)
    last_touch = verified_at if (verified_at and updated_at and verified_at > updated_at) else updated_at
    if last_touch is None:
        return "unknown", None
    if isinstance(last_touch, str):
        last_touch = datetime.fromisoformat(last_touch)
    if last_touch.tzinfo is None:
        last_touch = last_touch.replace(tzinfo=timezone.utc)
    days = (now - last_touch).days
    if days >= STALENESS_LOW:
        return "critical", days
    elif days >= STALENESS_MEDIUM:
        return "warning", days
    elif days >= STALENESS_HIGH:
        return "info", days
    return "ok", days


def _serialize(obj):
    """JSON serializer for datetime objects."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def export_cytoscape(conn):
    """Export full graph in Cytoscape.js format. Excludes content_embedding to keep export small."""
    node_rows = rows_to_dicts(conn.execute(
        "MATCH (n:Node) RETURN n.id, n.type, n.title, n.status, n.created_at, "
        "n.updated_at, n.verified_at, n.status_since, n.content, n.file_path, n.properties"
    ))

    nodes = []
    for row in node_rows:
        level, days = _staleness_level(row.get("n.updated_at"), row.get("n.verified_at"))
        nodes.append({
            "data": {
                "id": row["n.id"],
                "type": row.get("n.type"),
                "title": row.get("n.title"),
                "status": row.get("n.status"),
                "freshness_days": days,
                "staleness_level": level,
                "content": row.get("n.content"),
                "file_path": row.get("n.file_path"),
            }
        })

    edge_rows = rows_to_dicts(conn.execute("""
        MATCH (a:Node)-[e:Edge]->(b:Node)
        RETURN a.id AS source, b.id AS target,
               e.verb, e.since, e.until, e.source AS edge_source, e.note
    """))

    edges = []
    for row in edge_rows:
        verb_slug = row["e.verb"].replace(" ", "_")[:30] if row["e.verb"] else "rel"
        edge_id = f"{row['source']}__{row['target']}__{verb_slug}"
        edges.append({
            "data": {
                "id": edge_id,
                "source": row["source"],
                "target": row["target"],
                "verb": row["e.verb"],
                "active": row.get("e.until") is None,
            }
        })

    graph = {
        "elements": {
            "nodes": nodes,
            "edges": edges,
        },
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "node_count": len(nodes),
            "edge_count": len(edges),
        },
    }

    export_dir = get_export_dir()
    export_dir.mkdir(parents=True, exist_ok=True)
    out_path = export_dir / "graph.json"
    with open(out_path, "w") as f:
        json.dump(graph, f, indent=2, default=_serialize)

    return str(out_path), len(nodes), len(edges)


def export_json(conn):
    """Export raw graph as JSON (nodes + edges). Excludes content_embedding."""
    nodes = rows_to_dicts(conn.execute(
        "MATCH (n:Node) RETURN n.id, n.type, n.title, n.status, n.created_at, "
        "n.updated_at, n.verified_at, n.status_since, n.content, n.file_path, n.properties"
    ))
    edges = rows_to_dicts(conn.execute("""
        MATCH (a:Node)-[e:Edge]->(b:Node)
        RETURN a.id AS from_id, b.id AS to_id, e.*
    """))

    graph = {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }

    export_dir = get_export_dir()
    export_dir.mkdir(parents=True, exist_ok=True)
    out_path = export_dir / "graph_raw.json"
    with open(out_path, "w") as f:
        json.dump(graph, f, indent=2, default=_serialize)

    return str(out_path)


def export_batch(conn):
    """Export full graph as a replayable brain write batch.

    Produces a JSON array of create_node + create_edge operations
    that can rebuild the entire graph via: brain write batch --file <path>
    """
    ops = []

    nodes = rows_to_dicts(conn.execute(
        "MATCH (n:Node) RETURN n.id, n.type, n.title, n.status, n.created_at, "
        "n.updated_at, n.verified_at, n.status_since, n.content, n.file_path, n.properties"
    ))
    for row in nodes:
        op = {
            "op": "create_node",
            "id": row["n.id"],
            "type": row.get("n.type"),
            "title": row.get("n.title"),
            "status": row.get("n.status"),
            "content": row.get("n.content"),
            "file_path": row.get("n.file_path"),
        }
        if row.get("n.properties"):
            op["properties"] = row["n.properties"]
        if row.get("n.created_at"):
            op["created_at"] = str(row["n.created_at"])
        if row.get("n.verified_at"):
            op["verified_at"] = str(row["n.verified_at"])
        ops.append(op)

    edges = rows_to_dicts(conn.execute("""
        MATCH (a:Node)-[e:Edge]->(b:Node)
        RETURN a.id AS from_id, b.id AS to_id, e.verb, e.since, e.until, e.source, e.note
    """))
    for row in edges:
        op = {
            "op": "create_edge",
            "from": row["from_id"],
            "to": row["to_id"],
            "verb": row["e.verb"],
        }
        if row.get("e.since"):
            op["since"] = str(row["e.since"])
        if row.get("e.until"):
            op["until"] = str(row["e.until"])
        if row.get("e.source"):
            op["source"] = row["e.source"]
        if row.get("e.note"):
            op["note"] = row["e.note"]
        ops.append(op)

    export_dir = get_export_dir()
    export_dir.mkdir(parents=True, exist_ok=True)
    out_path = export_dir / "backup.json"
    with open(out_path, "w") as f:
        json.dump(ops, f, indent=2, default=_serialize)

    return str(out_path), len(nodes), len(edges)
