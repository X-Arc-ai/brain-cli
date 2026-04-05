"""Node and edge CRUD operations."""

import json
import sys
from datetime import datetime, timezone

from .config import VALID_STATUSES, get_all_types, get_immutable_types, get_tier_for_type, now


def _parse_ts(value):
    """Parse a timestamp string to datetime, or return None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _ts_param(dt):
    """Format datetime for Kuzu TIMESTAMP parameter."""
    if dt is None:
        return None
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


_VALID_FREQUENCIES = {"daily", "2x/week", "weekly", "biweekly", "monthly"}


def _validate_node(data, is_create=True):
    """Validate node data."""
    if is_create:
        for field in ("id", "type", "title"):
            if field not in data:
                raise ValueError(f"Missing required field: {field}")
        all_types = get_all_types()
        node_type = data["type"]
        if all_types and node_type not in all_types:
            tier = get_tier_for_type(node_type)
            if tier is None:
                print(f"Warning: type '{node_type}' is not registered in any tier. "
                      f"Register it with: brain config add-type {node_type} <tier>",
                      file=sys.stderr)
    if "status" in data and data["status"] not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {data['status']}. Valid: {sorted(VALID_STATUSES)}")
    props = data.get("properties")
    if isinstance(props, dict) and props.get("recurring"):
        if "frequency" not in props:
            raise ValueError("Recurring node requires 'frequency' in properties")
        if props["frequency"] not in _VALID_FREQUENCIES:
            raise ValueError(f"Invalid frequency: {props['frequency']}. Valid: {sorted(_VALID_FREQUENCIES)}")
        if "last_completed" not in props:
            raise ValueError("Recurring node requires 'last_completed' in properties (use 'never' if not yet completed)")


def create_node(conn, data):
    """Create a new node. Uses MERGE for idempotency."""
    _validate_node(data, is_create=True)
    ts = now()

    embedding = None
    try:
        from .embeddings import generate_embedding, node_text_for_embedding
        text = node_text_for_embedding(data)
        if text.strip():
            embedding = generate_embedding(text)
    except (RuntimeError, Exception) as e:
        print(f"Warning: embedding generation failed: {e}", file=sys.stderr)

    conn.execute(
        """
        MERGE (n:Node {id: $id})
        ON CREATE SET
            n.type = $type,
            n.title = $title,
            n.status = $status,
            n.created_at = timestamp($created_at),
            n.updated_at = timestamp($updated_at),
            n.verified_at = timestamp($verified_at),
            n.status_since = timestamp($status_since),
            n.content = $content,
            n.file_path = $file_path,
            n.properties = $properties,
            n.content_embedding = $embedding
        ON MATCH SET
            n.type = $type,
            n.title = $title,
            n.status = $status,
            n.updated_at = timestamp($updated_at),
            n.verified_at = timestamp($verified_at),
            n.status_since = timestamp($status_since),
            n.content = $content,
            n.file_path = $file_path,
            n.properties = $properties,
            n.content_embedding = $embedding
        """,
        parameters={
            "id": data["id"],
            "type": data["type"],
            "title": data["title"],
            "status": data.get("status"),
            "created_at": _ts_param(data.get("created_at", ts)),
            "updated_at": _ts_param(data.get("updated_at", ts)),
            "verified_at": _ts_param(data.get("verified_at")),
            "status_since": _ts_param(data.get("status_since", ts if data.get("status") else None)),
            "content": data.get("content"),
            "file_path": data.get("file_path"),
            "properties": json.dumps(data["properties"]) if "properties" in data and data["properties"] else None,
            "embedding": embedding,
        },
    )


def update_node(conn, data, maintenance=False):
    """Update an existing node. Rejects updates to immutable types unless maintenance mode."""
    if "id" not in data:
        raise ValueError("Missing required field: id")

    result = conn.execute(
        "MATCH (n:Node {id: $id}) RETURN n.type, n.id",
        parameters={"id": data["id"]},
    )
    columns = result.get_column_names()
    rows = []
    while result.has_next():
        rows.append(dict(zip(columns, result.get_next())))
    if not rows:
        raise ValueError(f"Node not found: {data['id']}")

    node_type = rows[0]["n.type"]
    immutable_types = get_immutable_types()
    if node_type in immutable_types:
        if maintenance:
            allowed_fields = {"id", "op", "status", "properties", "maintenance"}
            extra_fields = {k for k in data.keys() if not k.startswith("_")} - allowed_fields
            if extra_fields:
                raise ValueError(
                    f"Maintenance mode on immutable type '{node_type}' only allows status/properties updates. "
                    f"Unexpected fields: {extra_fields}"
                )
        else:
            raise ValueError(f"Cannot update immutable node type '{node_type}': {data['id']}")

    if "status" in data and data["status"] not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {data['status']}. Valid: {sorted(VALID_STATUSES)}")

    ts = now()
    sets = ["n.updated_at = timestamp($updated_at)"]
    params = {"id": data["id"], "updated_at": _ts_param(ts)}

    if "type" in data:
        all_types = get_all_types()
        if all_types and data["type"] not in all_types:
            tier = get_tier_for_type(data["type"])
            if tier is None:
                print(f"Warning: type '{data['type']}' is not registered in any tier.",
                      file=sys.stderr)
        sets.append("n.type = $type")
        params["type"] = data["type"]

    for field in ("title", "status", "content", "file_path"):
        if field in data:
            sets.append(f"n.{field} = ${field}")
            params[field] = data[field]

    if "status" in data:
        sets.append("n.status_since = timestamp($status_since)")
        params["status_since"] = _ts_param(
            _parse_ts(data["status_since"]) if "status_since" in data else ts
        )

    if "verified_at" in data:
        sets.append("n.verified_at = timestamp($verified_at)")
        params["verified_at"] = _ts_param(data["verified_at"])

    if "properties" in data:
        sets.append("n.properties = $properties")
        params["properties"] = json.dumps(data["properties"]) if data["properties"] else None

    if "title" in data or "content" in data:
        try:
            from .embeddings import generate_embedding, node_text_for_embedding
            current = conn.execute(
                "MATCH (n:Node {id: $id}) RETURN n.title, n.content",
                parameters={"id": data["id"]},
            )
            current_cols = current.get_column_names()
            current_row = {}
            if current.has_next():
                current_row = dict(zip(current_cols, current.get_next()))
            embed_data = {
                "title": data.get("title", current_row.get("n.title", "")),
                "content": data.get("content", current_row.get("n.content", "")),
            }
            text = node_text_for_embedding(embed_data)
            if text.strip():
                emb = generate_embedding(text)
                sets.append("n.content_embedding = $embedding")
                params["embedding"] = emb
        except (RuntimeError, Exception) as e:
            print(f"Warning: embedding generation failed: {e}", file=sys.stderr)

    query = f"MATCH (n:Node {{id: $id}}) SET {', '.join(sets)}"
    conn.execute(query, parameters=params)


def archive_node(conn, node_id):
    """Soft-delete: set status to archived."""
    ts = now()
    conn.execute(
        """
        MATCH (n:Node {id: $id})
        SET n.status = 'archived',
            n.status_since = timestamp($ts),
            n.updated_at = timestamp($ts)
        """,
        parameters={"id": node_id, "ts": _ts_param(ts)},
    )


def create_edge(conn, data):
    """Create a relationship edge. Validates both nodes exist first."""
    for field in ("from", "to", "verb"):
        if field not in data:
            raise ValueError(f"Missing required field: {field}")

    from_id = data["from"]
    to_id = data["to"]
    check = conn.execute(
        "MATCH (a:Node {id: $from_id}), (b:Node {id: $to_id}) RETURN a.id, b.id",
        parameters={"from_id": from_id, "to_id": to_id},
    )
    rows = []
    while check.has_next():
        rows.append(check.get_next())
    if not rows:
        missing = []
        for nid in (from_id, to_id):
            r = conn.execute("MATCH (n:Node {id: $id}) RETURN n.id", parameters={"id": nid})
            found = False
            while r.has_next():
                found = True
                r.get_next()
            if not found:
                missing.append(nid)
        raise ValueError(f"Edge not created: node(s) not found: {missing}")

    since = data.get("since", now())
    conn.execute(
        """
        MATCH (a:Node {id: $from_id}), (b:Node {id: $to_id})
        CREATE (a)-[e:Edge {
            verb: $verb,
            since: timestamp($since),
            until: timestamp($until),
            source: $source,
            note: $note
        }]->(b)
        """,
        parameters={
            "from_id": from_id,
            "to_id": to_id,
            "verb": data["verb"],
            "since": _ts_param(since),
            "until": _ts_param(data.get("until")),
            "source": data.get("source"),
            "note": data.get("note"),
        },
    )


def update_edge(conn, data):
    """Update an existing edge."""
    for field in ("from", "to", "verb"):
        if field not in data:
            raise ValueError(f"Missing required field: {field}")

    sets = []
    params = {
        "from_id": data["from"],
        "to_id": data["to"],
        "verb": data["verb"],
    }

    if "until" in data:
        sets.append("e.until = timestamp($until)")
        params["until"] = _ts_param(data["until"])

    if "source" in data:
        sets.append("e.source = $source")
        params["source"] = data["source"]

    if "note" in data:
        sets.append("e.note = $note")
        params["note"] = data["note"]

    if not sets:
        return

    query = f"""
        MATCH (a:Node {{id: $from_id}})-[e:Edge {{verb: $verb}}]->(b:Node {{id: $to_id}})
        SET {', '.join(sets)}
    """
    conn.execute(query, parameters=params)


def end_edge(conn, from_id, to_id, verb):
    """End a relationship by setting until = now."""
    ts = now()
    conn.execute(
        """
        MATCH (a:Node {id: $from_id})-[e:Edge {verb: $verb}]->(b:Node {id: $to_id})
        SET e.until = timestamp($ts)
        """,
        parameters={"from_id": from_id, "to_id": to_id, "verb": verb, "ts": _ts_param(ts)},
    )


def execute_batch(conn, operations):
    """Execute a batch of operations.

    Each operation is a dict with 'op' key.
    Valid ops: create_node, update_node, create_edge, update_edge, archive_node, end_edge
    Returns a list of results + a summary dict as the last element.
    """
    handlers = {
        "create_node": lambda op: create_node(conn, op),
        "update_node": lambda op: update_node(conn, op, maintenance=op.get("maintenance", False)),
        "create_edge": lambda op: create_edge(conn, op),
        "update_edge": lambda op: update_edge(conn, op),
        "archive_node": lambda op: archive_node(conn, op["id"]),
        "end_edge": lambda op: end_edge(conn, op["from"], op["to"], op["verb"]),
    }

    results = []
    created_nodes = 0
    created_edges = 0
    for i, op in enumerate(operations):
        op_type = op.get("op")
        if op_type not in handlers:
            raise ValueError(f"Operation {i}: unknown op '{op_type}'. Valid: {sorted(handlers.keys())}")
        try:
            handlers[op_type](op)
            results.append({"index": i, "op": op_type, "status": "ok"})
            if op_type == "create_node":
                created_nodes += 1
            elif op_type == "create_edge":
                created_edges += 1
        except Exception as e:
            raise ValueError(f"Operation {i} ({op_type}): {e}") from e

    summary = {
        "total": len(results),
        "created_nodes": created_nodes,
        "created_edges": created_edges,
    }
    results.append({"summary": summary})
    return results
