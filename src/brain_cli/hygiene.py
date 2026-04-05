import os
import re

from .config import (
    get_project_root,
    FILE_PATH_REQUIRED_TYPES,
    get_file_path_exceptions,
    DECOMPOSITION_VERBS,
    DECOMPOSITION_VERBS_INVERSE,
    BLOCKER_VERBS,
)
from .utils import rows_to_dicts


def find_duplicates(conn):
    """Find potential duplicate nodes (same title, different IDs)."""
    result = conn.execute("""
        MATCH (a:Node), (b:Node)
        WHERE a.title = b.title AND a.id < b.id AND a.type = b.type
        RETURN a.id AS id_a, b.id AS id_b, a.title AS title, a.type AS type
        ORDER BY a.title
    """)
    return rows_to_dicts(result)


def find_orphans(conn):
    """Find disconnected nodes (no edges at all)."""
    result = conn.execute("""
        MATCH (n:Node)
        WHERE NOT EXISTS {
            MATCH (n)-[e:Edge]-()
        }
        RETURN n.id, n.title, n.type, n.status
        ORDER BY n.type, n.title
    """)
    return rows_to_dicts(result)


def audit_verbs(conn):
    """List all relationship verbs with counts."""
    result = conn.execute("""
        MATCH ()-[e:Edge]->()
        RETURN e.verb AS verb, count(*) AS count
        ORDER BY count DESC
    """)
    return rows_to_dicts(result)


# --- Edge schema rules ---
# Each rule: (node_type, required_edge_direction, required_target_types, required_verbs, description)
EDGE_RULES = [
    {
        "node_type": "goal",
        "check": "outgoing",
        "target_types": ["person"],
        "verbs": ["assigned to", "owned by", "managed by"],
        "description": "Every goal must have a person (assigned to / owned by)",
    },
    {
        "node_type": "goal",
        "check": "outgoing",
        "target_types": ["company", "project", "product"],
        "verbs": ["goal for"],
        "description": "Every goal must link to a company/project/product (goal for)",
    },
    {
        "node_type": "blocker",
        "check": "any",
        "target_types": None,  # any type
        "verbs": ["affects", "blocks", "blocked by"],
        "description": "Every blocker must have an affects/blocks/blocked by edge",
    },
    {
        "node_type": "task",
        "check": "outgoing",
        "target_types": ["person"],
        "verbs": ["assigned to", "owned by", "managed by"],
        "description": "Every task must have a person (assigned to / owned by)",
    },
]


def check_completeness(conn):
    """Check edge schema completeness -- every node type has required edges.

    Returns a list of violations: nodes missing required edges.
    """
    violations = []

    for rule in EDGE_RULES:
        node_type = rule["node_type"]
        verbs = rule["verbs"]
        description = rule["description"]

        # Get all non-archived nodes of this type
        result = conn.execute(
            "MATCH (n:Node) WHERE n.type = $type AND n.status <> 'archived' RETURN n.id, n.title",
            parameters={"type": node_type},
        )
        nodes = rows_to_dicts(result)

        # Build target type filter from rule
        target_types = rule.get("target_types")
        type_filter = ""
        if target_types:
            type_list = ", ".join(f"'{t}'" for t in target_types)
            type_filter = f" AND t.type IN [{type_list}]"

        for node in nodes:
            node_id = node["n.id"]
            has_required = False

            if rule["check"] in ("outgoing", "any"):
                # Check outgoing edges with matching verbs and target types
                verb_filter = " OR ".join(f"e.verb = '{v}'" for v in verbs)
                r = conn.execute(
                    f"MATCH (n:Node {{id: $id}})-[e:Edge]->(t:Node) WHERE ({verb_filter}){type_filter} AND e.until IS NULL RETURN count(*) AS cnt",
                    parameters={"id": node_id},
                )
                rows = rows_to_dicts(r)
                if rows and rows[0]["cnt"] > 0:
                    has_required = True

            if not has_required and rule["check"] in ("incoming", "any"):
                # Check incoming edges with matching verbs and target types
                verb_filter = " OR ".join(f"e.verb = '{v}'" for v in verbs)
                r = conn.execute(
                    f"MATCH (t:Node)-[e:Edge]->(n:Node {{id: $id}}) WHERE ({verb_filter}){type_filter} AND e.until IS NULL RETURN count(*) AS cnt",
                    parameters={"id": node_id},
                )
                rows = rows_to_dicts(r)
                if rows and rows[0]["cnt"] > 0:
                    has_required = True

            if not has_required:
                violations.append({
                    "node_id": node_id,
                    "node_title": node["n.title"],
                    "node_type": node_type,
                    "rule": description,
                    "missing_verbs": verbs,
                })

    return violations


def check_file_paths(conn):
    """Validate file_path on structural nodes.

    Check 1: Active structural nodes (per FILE_PATH_REQUIRED_TYPES) should have file_path.
    Check 2: All file_paths should resolve to existing files on disk.

    Known exceptions loaded from config via get_file_path_exceptions().
    """
    known_exceptions = get_file_path_exceptions()
    project_root = get_project_root()

    violations = []

    # Check 1: Active structural nodes without file_path
    must_have = ", ".join(f"'{t}'" for t in FILE_PATH_REQUIRED_TYPES)
    result = conn.execute(f"""
        MATCH (n:Node)
        WHERE n.type IN [{must_have}]
          AND n.status IN ['active', 'in_progress', 'pending']
          AND (n.file_path IS NULL OR n.file_path = '')
        RETURN n.id, n.title, n.type, n.status
        ORDER BY n.type, n.id
    """)
    for row in rows_to_dicts(result):
        node_id = row["n.id"]
        if node_id in known_exceptions:
            continue
        violations.append({
            "node_id": node_id,
            "node_title": row["n.title"],
            "node_type": row["n.type"],
            "check": "missing_file_path",
            "message": f"Active {row['n.type']} node without file_path",
        })

    # Check 2: All file_paths resolve to existing FILES (not directories)
    result = conn.execute("""
        MATCH (n:Node)
        WHERE n.file_path IS NOT NULL AND n.file_path <> ''
        RETURN n.id, n.title, n.type, n.file_path
        ORDER BY n.type, n.id
    """)
    for row in rows_to_dicts(result):
        file_path = row["n.file_path"]
        full_path = project_root / file_path
        if not os.path.exists(full_path):
            violations.append({
                "node_id": row["n.id"],
                "node_title": row["n.title"],
                "node_type": row["n.type"],
                "check": "broken_file_path",
                "file_path": file_path,
                "resolved_to": str(full_path),
                "message": f"file_path does not exist on disk: {file_path}",
            })
        elif os.path.isdir(full_path):
            violations.append({
                "node_id": row["n.id"],
                "node_title": row["n.title"],
                "node_type": row["n.type"],
                "check": "directory_file_path",
                "file_path": file_path,
                "resolved_to": str(full_path),
                "message": f"file_path points to a directory, not a file: {file_path}",
            })

    return violations


def check_content_drift(conn):
    """Compare brain content against context files for structural nodes.

    Detects:
    1. Thin brain content: context file has significantly more detail than brain
    2. Missing sections: key section headers in file not reflected in brain content

    Only checks nodes with both content and file_path set.
    """
    project_root = get_project_root()
    issues = []

    result = conn.execute("""
        MATCH (n:Node)
        WHERE n.file_path IS NOT NULL AND n.file_path <> ''
          AND n.content IS NOT NULL AND n.content <> ''
          AND n.status IN ['active', 'in_progress', 'pending', 'blocked']
        RETURN n.id, n.type, n.title, n.content, n.file_path, n.updated_at
        ORDER BY n.type, n.id
    """)
    nodes = rows_to_dicts(result)

    for node in nodes:
        file_path = node["n.file_path"]
        full_path = project_root / file_path
        if not os.path.isfile(full_path):
            continue

        try:
            file_content = full_path.read_text(encoding="utf-8")
        except Exception:
            continue

        brain_content = node["n.content"] or ""
        brain_len = len(brain_content)
        file_len = len(file_content)
        node_id = node["n.id"]
        node_info = {
            "node_id": node_id,
            "node_title": node["n.title"],
            "node_type": node["n.type"],
            "file_path": file_path,
        }

        # Check 1: Thin brain content (file is 3x+ longer and brain is under 500 chars)
        if brain_len < 500 and file_len > brain_len * 3:
            issues.append({
                **node_info,
                "check": "thin_brain_content",
                "brain_chars": brain_len,
                "file_chars": file_len,
                "ratio": round(file_len / max(brain_len, 1), 1),
                "message": f"Brain content ({brain_len} chars) much thinner than file ({file_len} chars). Enrich brain content.",
            })

        # Check 2: Key section headers in file missing from brain
        # Extract markdown headers from file
        file_headers = set()
        for match in re.finditer(r'^#{1,3}\s+(.+)$', file_content, re.MULTILINE):
            header = match.group(1).strip().lower()
            # Skip generic administrative headers not expected in brain summaries
            if header not in {"---"}:
                file_headers.add(header)

        brain_lower = brain_content.lower()
        missing_sections = []
        for header in file_headers:
            # Check if key words from header appear in brain content
            key_words = [w for w in header.split() if len(w) > 3]
            if key_words and not any(w in brain_lower for w in key_words):
                missing_sections.append(header)

        if len(missing_sections) >= 3:
            issues.append({
                **node_info,
                "check": "missing_sections",
                "missing_count": len(missing_sections),
                "missing_sections": missing_sections[:5],
                "message": f"File has {len(missing_sections)} sections not reflected in brain content.",
            })

    return issues


def check_operational_readiness(conn):
    """Check that active operational nodes have decomposition or blockers.

    Principle: any non-informative node in an active status must have either:
    - Child work items (tasks, subtasks) -> forward motion
    - Blocker edges -> clear impediment
    - Or it shouldn't be in that status

    Applies to goals (active/in_progress/pending) and pending decisions.
    """
    violations = []

    # Goals: must have tasks or blockers
    goal_result = conn.execute("""
        MATCH (g:Node)
        WHERE g.type = 'goal'
          AND g.status IN ['active', 'in_progress', 'pending']
        RETURN g.id AS id, g.title AS title, g.status AS status
    """)
    goals = rows_to_dicts(goal_result)

    decomp_verbs = " OR ".join(f"e.verb = '{v}'" for v in DECOMPOSITION_VERBS)
    decomp_verbs_inv = " OR ".join(f"e.verb = '{v}'" for v in DECOMPOSITION_VERBS_INVERSE)
    blocker_verbs = " OR ".join(f"e.verb = '{v}'" for v in BLOCKER_VERBS)

    for row in goals:
        gid = row["id"]

        # Check for outgoing decomposition edges (goal -> task)
        r = conn.execute(
            f"MATCH (g:Node {{id: $id}})-[e:Edge]->(t:Node) "
            f"WHERE ({decomp_verbs}) AND e.until IS NULL AND t.type = 'task' "
            f"RETURN count(*) AS cnt",
            parameters={"id": gid}
        )
        has_tasks_out = rows_to_dicts(r)[0]["cnt"]

        # Check for incoming decomposition edges (task -> goal)
        r = conn.execute(
            f"MATCH (t:Node)-[e:Edge]->(g:Node {{id: $id}}) "
            f"WHERE ({decomp_verbs_inv}) AND e.until IS NULL AND t.type = 'task' "
            f"RETURN count(*) AS cnt",
            parameters={"id": gid}
        )
        has_tasks_in = rows_to_dicts(r)[0]["cnt"]

        # Check for blocker edges
        r = conn.execute(
            f"MATCH (g:Node {{id: $id}})-[e:Edge]-(b:Node) "
            f"WHERE ({blocker_verbs}) AND e.until IS NULL "
            f"RETURN count(*) AS cnt",
            parameters={"id": gid}
        )
        has_blockers = rows_to_dicts(r)[0]["cnt"]

        if has_tasks_out == 0 and has_tasks_in == 0 and has_blockers == 0:
            violations.append({
                "node_id": gid,
                "node_type": "goal",
                "title": row["title"],
                "status": row["status"],
                "issue": "Active goal with no tasks and no blockers",
                "action": "Decompose into tasks, add blockers, or change status"
            })

    # Decisions: pending decisions should have impact edges
    decision_result = conn.execute("""
        MATCH (d:Node)
        WHERE d.type = 'decision' AND d.status = 'pending'
        RETURN d.id AS id, d.title AS title
    """)
    decisions = rows_to_dicts(decision_result)

    for row in decisions:
        did = row["id"]
        r = conn.execute(
            "MATCH (d:Node {id: $id})-[e:Edge]-(t:Node) "
            "WHERE e.until IS NULL "
            "RETURN count(*) AS cnt",
            parameters={"id": did}
        )
        has_impact = rows_to_dicts(r)[0]["cnt"]

        if has_impact == 0:
            violations.append({
                "node_id": did,
                "node_type": "decision",
                "title": row["title"],
                "status": "pending",
                "issue": "Pending decision with no connected nodes",
                "action": "Link to what this decision affects or archive"
            })

    return violations
