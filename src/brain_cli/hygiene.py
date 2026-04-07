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

    Issues a single parameterized query per rule using NOT EXISTS subqueries
    to find nodes missing required outgoing/incoming/any edges.
    """
    violations = []

    for rule in EDGE_RULES:
        node_type = rule["node_type"]
        verbs = rule["verbs"]
        target_types = rule.get("target_types")
        check_kind = rule["check"]
        description = rule["description"]

        # Build the type-filter clause as a parameterized predicate
        type_predicate = "AND t.type IN $target_types " if target_types else ""

        if check_kind == "outgoing":
            cypher = f"""
                MATCH (n:Node)
                WHERE n.type = $type AND n.status <> 'archived'
                  AND NOT EXISTS {{
                    MATCH (n)-[e:Edge]->(t:Node)
                    WHERE e.verb IN $verbs AND e.until IS NULL {type_predicate}
                  }}
                RETURN n.id AS id, n.title AS title
            """
        elif check_kind == "incoming":
            cypher = f"""
                MATCH (n:Node)
                WHERE n.type = $type AND n.status <> 'archived'
                  AND NOT EXISTS {{
                    MATCH (t:Node)-[e:Edge]->(n)
                    WHERE e.verb IN $verbs AND e.until IS NULL {type_predicate}
                  }}
                RETURN n.id AS id, n.title AS title
            """
        else:  # "any"
            cypher = f"""
                MATCH (n:Node)
                WHERE n.type = $type AND n.status <> 'archived'
                  AND NOT EXISTS {{
                    MATCH (n)-[e:Edge]-(t:Node)
                    WHERE e.verb IN $verbs AND e.until IS NULL {type_predicate}
                  }}
                RETURN n.id AS id, n.title AS title
            """

        params = {"type": node_type, "verbs": verbs}
        if target_types:
            params["target_types"] = target_types

        for row in rows_to_dicts(conn.execute(cypher, parameters=params)):
            violations.append({
                "node_id": row["id"],
                "node_title": row["title"],
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

    Single parameterized query per category. Goals failing all three checks
    (outgoing decomposition, incoming decomposition, blocker edges) are
    flagged in one pass.
    """
    violations = []

    # Goals: missing all three of {outgoing decomp, incoming decomp, blockers}
    goal_query = """
        MATCH (g:Node)
        WHERE g.type = 'goal'
          AND g.status IN ['active', 'in_progress', 'pending']
          AND NOT EXISTS {
            MATCH (g)-[e:Edge]->(t:Node)
            WHERE e.verb IN $decomp_verbs AND e.until IS NULL AND t.type = 'task'
          }
          AND NOT EXISTS {
            MATCH (t:Node)-[e:Edge]->(g)
            WHERE e.verb IN $decomp_verbs_inv AND e.until IS NULL AND t.type = 'task'
          }
          AND NOT EXISTS {
            MATCH (g)-[e:Edge]-(b:Node)
            WHERE e.verb IN $blocker_verbs AND e.until IS NULL
          }
        RETURN g.id AS id, g.title AS title, g.status AS status
    """
    for row in rows_to_dicts(conn.execute(goal_query, parameters={
        "decomp_verbs": list(DECOMPOSITION_VERBS),
        "decomp_verbs_inv": list(DECOMPOSITION_VERBS_INVERSE),
        "blocker_verbs": list(BLOCKER_VERBS),
    })):
        violations.append({
            "node_id": row["id"],
            "node_type": "goal",
            "title": row["title"],
            "status": row["status"],
            "issue": "Active goal with no tasks and no blockers",
            "action": "Decompose into tasks, add blockers, or change status",
        })

    # Decisions: pending decisions with no connected (active) nodes
    decision_query = """
        MATCH (d:Node)
        WHERE d.type = 'decision' AND d.status = 'pending'
          AND NOT EXISTS {
            MATCH (d)-[e:Edge]-(t:Node)
            WHERE e.until IS NULL
          }
        RETURN d.id AS id, d.title AS title
    """
    for row in rows_to_dicts(conn.execute(decision_query)):
        violations.append({
            "node_id": row["id"],
            "node_type": "decision",
            "title": row["title"],
            "status": "pending",
            "issue": "Pending decision with no connected nodes",
            "action": "Link to what this decision affects or archive",
        })

    return violations
