"""Graph read operations -- scan, context, search, queries."""

from .utils import rows_to_dicts, parse_props


def _format_node(row, prefix="n."):
    """Format a node row dict for output."""
    return {k.replace(prefix, ""): v for k, v in row.items() if k.startswith(prefix)}


def get_node(conn, node_id):
    """Get a node by ID with all its edges."""
    result = conn.execute(
        "MATCH (n:Node {id: $id}) RETURN n.*",
        parameters={"id": node_id},
    )
    rows = rows_to_dicts(result)
    if not rows:
        return None

    node = _format_node(rows[0])
    if "properties" in node:
        node["properties"] = parse_props(node["properties"])

    result = conn.execute(
        """
        MATCH (n:Node {id: $id})-[e:Edge]->(t:Node)
        RETURN e.verb, e.since, e.until, e.source, e.note,
               t.id AS target_id, t.title AS target_title, t.type AS target_type
        """,
        parameters={"id": node_id},
    )
    node["edges_out"] = rows_to_dicts(result)

    result = conn.execute(
        """
        MATCH (s:Node)-[e:Edge]->(n:Node {id: $id})
        RETURN e.verb, e.since, e.until, e.source, e.note,
               s.id AS source_id, s.title AS source_title, s.type AS source_type
        """,
        parameters={"id": node_id},
    )
    node["edges_in"] = rows_to_dicts(result)

    return node


def get_context(conn, node_id, depth=1):
    """Deep context: node + all connected nodes with full content at N hops."""
    root = get_node(conn, node_id)
    if root is None:
        return None

    result = conn.execute(
        """
        MATCH (n:Node {id: $id})-[e:Edge]-(connected:Node)
        RETURN DISTINCT connected.id, connected.type, connected.title,
               connected.status, connected.content, connected.status_since,
               connected.updated_at, connected.verified_at,
               connected.file_path, connected.properties
        """,
        parameters={"id": node_id},
    )
    connected_nodes = {}
    for row in rows_to_dicts(result):
        cid = row["connected.id"]
        if cid not in connected_nodes:
            connected_nodes[cid] = {
                "id": cid,
                "type": row["connected.type"],
                "title": row["connected.title"],
                "status": row["connected.status"],
                "content": row["connected.content"],
                "status_since": row.get("connected.status_since"),
                "updated_at": row.get("connected.updated_at"),
                "verified_at": row.get("connected.verified_at"),
                "file_path": row.get("connected.file_path"),
                "properties": parse_props(row.get("connected.properties")),
            }

    if depth > 1:
        result = conn.execute(
            f"""
            MATCH p = (n:Node {{id: $id}})-[e:Edge* 1..{depth}]-(connected:Node)
            RETURN DISTINCT connected.id, connected.type, connected.title,
                   connected.status, connected.content, connected.status_since,
                   connected.updated_at, connected.verified_at,
                   connected.file_path, connected.properties
            """,
            parameters={"id": node_id},
        )
        for row in rows_to_dicts(result):
            cid = row["connected.id"]
            if cid not in connected_nodes and cid != node_id:
                connected_nodes[cid] = {
                    "id": cid,
                    "type": row["connected.type"],
                    "title": row["connected.title"],
                    "status": row["connected.status"],
                    "content": row["connected.content"],
                    "status_since": row.get("connected.status_since"),
                    "updated_at": row.get("connected.updated_at"),
                    "verified_at": row.get("connected.verified_at"),
                    "file_path": row.get("connected.file_path"),
                    "properties": parse_props(row.get("connected.properties")),
                }

    grouped = {}
    for node in connected_nodes.values():
        t = node["type"] or "unknown"
        if t not in grouped:
            grouped[t] = []
        grouped[t].append(node)

    root["connected"] = grouped
    root["connected_count"] = len(connected_nodes)
    return root


def scan_subgraph(conn, node_id, depth=3):
    """Topology scan with progressive detail: N-hop subgraph.

    Root + hop 1: includes content + properties.
    Hop 2+: lightweight metadata only.
    """
    result = conn.execute(
        "MATCH (n:Node {id: $id}) RETURN n.id, n.type, n.title, n.status, n.file_path, n.content, n.properties",
        parameters={"id": node_id},
    )
    rows = rows_to_dicts(result)
    if not rows:
        return None
    root = {k.replace("n.", ""): v for k, v in rows[0].items()}
    if root.get("properties"):
        root["properties"] = parse_props(root["properties"])

    visited = {node_id}
    frontier = [node_id]
    nodes_by_hop = {}

    for hop in range(1, depth + 1):
        if not frontier:
            break

        if hop == 1:
            result = conn.execute(
                """
                MATCH (a:Node)-[e:Edge]-(b:Node)
                WHERE a.id IN $frontier AND e.until IS NULL
                RETURN DISTINCT b.id, b.type, b.title, b.status, b.file_path, b.content, b.properties
                """,
                parameters={"frontier": frontier},
            )
        else:
            result = conn.execute(
                """
                MATCH (a:Node)-[e:Edge]-(b:Node)
                WHERE a.id IN $frontier AND e.until IS NULL
                RETURN DISTINCT b.id, b.type, b.title, b.status, b.file_path
                """,
                parameters={"frontier": frontier},
            )

        next_frontier = []
        hop_nodes = []
        for row in rows_to_dicts(result):
            nid = row["b.id"]
            if nid not in visited:
                visited.add(nid)
                next_frontier.append(nid)
                node_data = {
                    "id": nid,
                    "type": row["b.type"],
                    "title": row["b.title"],
                    "status": row["b.status"],
                    "file_path": row.get("b.file_path"),
                }
                if hop == 1:
                    node_data["content"] = row.get("b.content")
                    props = row.get("b.properties")
                    node_data["properties"] = parse_props(props) if props else None
                hop_nodes.append(node_data)

        if hop_nodes:
            nodes_by_hop[hop] = hop_nodes
        frontier = next_frontier

    all_ids = list(visited)
    result = conn.execute(
        """
        MATCH (a:Node)-[e:Edge]->(b:Node)
        WHERE a.id IN $ids AND b.id IN $ids AND e.until IS NULL
        RETURN a.id AS source, e.verb AS verb, b.id AS target
        ORDER BY a.id, e.verb, b.id
        """,
        parameters={"ids": all_ids},
    )
    edges = rows_to_dicts(result)

    return {
        "root": root,
        "scan_depth": depth,
        "total_nodes": len(visited),
        "nodes_by_hop": nodes_by_hop,
        "edges": edges,
    }


def query_cypher(conn, cypher_query):
    """Execute raw Cypher and return results as list of dicts."""
    result = conn.execute(cypher_query)
    return rows_to_dicts(result)


def query_depends_on(conn, node_id):
    """What depends on node X? (incoming dependency edges)"""
    result = conn.execute(
        """
        MATCH (dep:Node)-[e:Edge]->(target:Node {id: $id})
        WHERE e.verb IN ['depends on', 'cannot start until', 'blocked by', 'requires']
          AND e.until IS NULL
        RETURN dep.id, dep.title, dep.type, dep.status, e.verb
        ORDER BY dep.type, dep.title
        """,
        parameters={"id": node_id},
    )
    return rows_to_dicts(result)


def query_blast_radius(conn, node_id, hops=3):
    """N-hop subgraph from a node."""
    result = conn.execute(
        f"""
        MATCH p = (anchor:Node {{id: $id}})-[e:Edge* 1..{hops}]-(connected:Node)
        RETURN DISTINCT connected.id, connected.title, connected.type, connected.status,
               length(p) AS distance
        ORDER BY distance, connected.type
        """,
        parameters={"id": node_id},
    )
    return rows_to_dicts(result)


def query_chain(conn, node_id):
    """Full dependency chain (iterative BFS, max depth 10)."""
    dep_verbs = ['depends on', 'cannot start until', 'blocked by', 'requires']
    visited = set()
    results = []
    frontier = [node_id]
    depth = 0

    while frontier and depth < 10:
        depth += 1
        next_frontier = []
        for nid in frontier:
            result = conn.execute(
                """
                MATCH (n:Node {id: $id})-[e:Edge]->(dep:Node)
                WHERE e.verb IN $verbs AND e.until IS NULL
                RETURN dep.id, dep.title, dep.type, dep.status
                """,
                parameters={"id": nid, "verbs": dep_verbs},
            )
            for row in rows_to_dicts(result):
                did = row["dep.id"]
                if did not in visited:
                    visited.add(did)
                    row["depth"] = depth
                    results.append(row)
                    next_frontier.append(did)
        frontier = next_frontier

    return results


def query_changed_since(conn, date_str):
    """Nodes updated after a given date."""
    result = conn.execute(
        """
        MATCH (n:Node)
        WHERE n.updated_at > cast($date AS TIMESTAMP)
        RETURN n.id, n.title, n.type, n.status, n.updated_at
        ORDER BY n.updated_at DESC
        """,
        parameters={"date": date_str},
    )
    return rows_to_dicts(result)


def query_stale(conn, threshold_days=14):
    """Nodes with freshness > threshold days."""
    result = conn.execute(
        """
        MATCH (n:Node)
        WHERE n.status IN ['active', 'in_progress', 'pending', 'blocked']
          AND NOT n.type IN ['event', 'status_change', 'observation']
        RETURN n.id, n.title, n.type, n.status,
               n.updated_at, n.verified_at
        ORDER BY n.updated_at ASC
        """,
    )
    rows = rows_to_dicts(result)
    from datetime import datetime, timezone
    now_dt = datetime.now(timezone.utc)
    stale = []
    for row in rows:
        updated = row.get("n.updated_at")
        verified = row.get("n.verified_at")
        last_touch = verified if (verified and updated and verified > updated) else updated
        if last_touch is None:
            continue
        if isinstance(last_touch, str):
            last_touch = datetime.fromisoformat(last_touch)
        if last_touch.tzinfo is None:
            last_touch = last_touch.replace(tzinfo=timezone.utc)
        days = (now_dt - last_touch).days
        if days >= threshold_days:
            row["days_stale"] = days
            if days >= 30:
                row["level"] = "CRITICAL"
            elif days >= 14:
                row["level"] = "WARNING"
            else:
                row["level"] = "INFO"
            stale.append(row)
    return stale


def query_person(conn, person_id):
    """Full person assessment subgraph."""
    person_node = get_node(conn, person_id)

    out = conn.execute(
        """
        MATCH (p:Node {id: $id})-[e:Edge]->(connected:Node)
        WHERE e.until IS NULL
        RETURN connected.id, connected.title, connected.type, connected.status, e.verb,
               connected.file_path, connected.properties,
               'outgoing' AS direction
        ORDER BY connected.type, connected.title
        """,
        parameters={"id": person_id},
    )
    connections = []
    for row in rows_to_dicts(out):
        row["connected.properties"] = parse_props(row.get("connected.properties"))
        connections.append(row)

    inc = conn.execute(
        """
        MATCH (connected:Node)-[e:Edge]->(p:Node {id: $id})
        WHERE e.until IS NULL
        RETURN connected.id, connected.title, connected.type, connected.status, e.verb,
               connected.file_path, connected.properties,
               'incoming' AS direction
        ORDER BY connected.type, connected.title
        """,
        parameters={"id": person_id},
    )
    for row in rows_to_dicts(inc):
        row["connected.properties"] = parse_props(row.get("connected.properties"))
        connections.append(row)

    return {
        "person": person_node,
        "connections": connections,
    }


def get_all_nodes_for_embedding(conn):
    """Fetch all non-archived nodes for embedding generation."""
    result = conn.execute(
        "MATCH (n:Node) "
        "WHERE n.status <> 'archived' OR n.status IS NULL "
        "RETURN n.id, n.title, n.content, n.content_embedding IS NOT NULL AS has_embedding "
        "ORDER BY n.id"
    )
    return rows_to_dicts(result)


def search_semantic(conn, query, type_filter=None, top_k=10, expand=False):
    """Semantic search using cosine similarity on stored embeddings."""
    import math
    from .embeddings import generate_embedding

    query_embedding = generate_embedding(query)

    type_clause = "AND n.type = $type" if type_filter else ""
    params = {}
    if type_filter:
        params["type"] = type_filter

    result = conn.execute(
        f"MATCH (n:Node) "
        f"WHERE n.content_embedding IS NOT NULL {type_clause} "
        f"RETURN n.id AS id, n.type AS type, n.title AS title, "
        f"  n.status AS status, n.content AS content, "
        f"  n.file_path AS file_path, n.properties AS properties, "
        f"  n.content_embedding AS embedding",
        parameters=params,
    )
    rows = rows_to_dicts(result)

    def _cosine_distance(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 2.0
        return 1.0 - dot / (norm_a * norm_b)

    for row in rows:
        emb = row.pop("embedding", None)
        if emb:
            row["distance"] = round(_cosine_distance(query_embedding, emb), 6)
        else:
            row["distance"] = 2.0

    rows.sort(key=lambda r: r["distance"])
    rows = rows[:top_k]

    for row in rows:
        if "properties" in row:
            row["properties"] = parse_props(row["properties"])

    if expand:
        for row in rows:
            edge_result = conn.execute(
                "MATCH (n:Node {id: $id})-[e:Edge]-(connected:Node) "
                "WHERE e.until IS NULL "
                "RETURN DISTINCT connected.id AS cid, connected.title AS ctitle, "
                "  connected.type AS ctype, e.verb AS verb",
                parameters={"id": row["id"]},
            )
            connections = []
            for er in rows_to_dicts(edge_result):
                connections.append({
                    "id": er["cid"],
                    "title": er["ctitle"],
                    "type": er["ctype"],
                    "verb": er["verb"],
                })
            row["connections"] = connections

    return rows


def search_nodes(conn, query, type_filter=None):
    """Full-text search across node titles, content, and IDs."""
    params = {"q": query.lower()}

    type_clause = ""
    if type_filter:
        type_clause = "AND n.type = $type"
        params["type"] = type_filter

    result = conn.execute(
        f"""
        MATCH (n:Node)
        WHERE (lower(n.title) CONTAINS lower($q)
            OR lower(n.content) CONTAINS lower($q)
            OR lower(n.id) CONTAINS lower($q))
        {type_clause}
        RETURN n.id, n.type, n.title, n.status, n.content, n.file_path
        ORDER BY n.type, n.title
        """,
        parameters=params,
    )
    rows = rows_to_dicts(result)

    ql = query.lower()
    for row in rows:
        content = row.get("n.content") or ""
        idx = content.lower().find(ql)
        if idx >= 0:
            start = max(0, idx - 60)
            end = min(len(content), idx + len(query) + 60)
            snippet = ("..." if start > 0 else "") + content[start:end] + ("..." if end < len(content) else "")
            row["match_snippet"] = snippet
        elif (row.get("n.title") or "").lower().find(ql) >= 0:
            row["match_snippet"] = f"(matched in title: {row['n.title']})"
        else:
            row["match_snippet"] = f"(matched in id: {row['n.id']})"

    return rows


def get_stats(conn):
    """Node/edge counts by type, including embedding coverage."""
    node_result = conn.execute(
        "MATCH (n:Node) RETURN n.type AS type, count(*) AS count ORDER BY type"
    )
    edge_result = conn.execute(
        "MATCH ()-[e:Edge]->() RETURN e.verb AS verb, count(*) AS count ORDER BY count DESC"
    )
    nodes = rows_to_dicts(node_result)
    edges = rows_to_dicts(edge_result)

    total_nodes = sum(r["count"] for r in nodes)
    total_edges = sum(r["count"] for r in edges)

    emb_result = conn.execute(
        "MATCH (n:Node) RETURN "
        "count(CASE WHEN n.content_embedding IS NOT NULL THEN 1 END) AS with_embeddings"
    )
    emb_rows = rows_to_dicts(emb_result)
    nodes_with_embeddings = emb_rows[0]["with_embeddings"] if emb_rows else 0

    return {
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "nodes_with_embeddings": nodes_with_embeddings,
        "nodes_by_type": nodes,
        "edges_by_verb": edges,
    }
