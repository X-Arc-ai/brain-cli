"""brain replay -- Mine conversation history for graph updates.

6-stage pipeline:
  A. Broad keyword sweep on indexed conversation store
  B. Entity-specific queries for structural nodes
  C. Semantic/topic-based sweep
  D. Filter against current graph state
  E. Build proposals
  F. Confirm and execute via writer.execute_batch()

Requires xarc-memory (optional dependency): pip install 'xarc-brain[memory]'
"""

import hashlib

import click

from .reader import search_nodes, get_node
from .utils import rows_to_dicts


# --- Adapter: sole coupling point to xarc-memory ---

def _require_memory():
    """Lazy-import xarc-memory. Raises RuntimeError with install instructions if missing."""
    try:
        import memory
        return memory
    except ImportError:
        raise RuntimeError(
            "xarc-memory is required for replay. "
            "Install it with: pip install 'xarc-brain[memory]'"
        )


def _memory_search(mem, query, limit=20, since_days=None):
    """Search the conversation store via xarc-memory.

    Adapts to whichever search interface xarc-memory exposes.
    Returns a list of dicts with at least 'text' and optionally 'date', 'session_id'.
    """
    try:
        # Try the expected search API
        if hasattr(mem, "search"):
            results = mem.search(query, limit=limit)
        elif hasattr(mem, "query"):
            results = mem.query(query, limit=limit)
        else:
            # Try the searcher submodule
            from memory.searcher import search as mem_search
            results = mem_search(query, limit=limit)

        # Normalize results to list of dicts
        if not results:
            return []
        normalized = []
        for r in results:
            if isinstance(r, dict):
                normalized.append(r)
            elif isinstance(r, str):
                normalized.append({"text": r})
            else:
                normalized.append({"text": str(r)})
        return normalized
    except Exception:
        return []


# --- Stage functions ---

_BROAD_KEYWORDS = [
    "decision", "shipped", "blocked", "changed", "new",
    "FYI", "update", "correction",
]


def _stage_broad_sweep(mem, since_days):
    """Stage A: Keyword queries on the indexed conversation store."""
    candidates = []
    for keyword in _BROAD_KEYWORDS:
        results = _memory_search(mem, keyword, limit=20, since_days=since_days)
        for r in results:
            entry = dict(r)
            entry["_stage"] = "broad_sweep"
            entry["_keyword"] = keyword
            candidates.append(entry)
    return candidates


def _stage_entity_sweep(mem, conn, since_days):
    """Stage B: For each structural node, query conversation store by title."""
    candidates = []
    structural = rows_to_dicts(conn.execute(
        "MATCH (n:Node) WHERE n.type IN ['project', 'person', 'company', 'product'] "
        "AND n.status <> 'archived' RETURN n.id, n.title, n.type"
    ))
    for node in structural:
        title = node.get("n.title", "")
        if not title or len(title) < 3:
            continue
        results = _memory_search(mem, title, limit=10, since_days=since_days)
        for r in results:
            entry = dict(r)
            entry["_stage"] = "entity_sweep"
            entry["_entity_id"] = node["n.id"]
            entry["_entity_title"] = title
            candidates.append(entry)
    return candidates


_TOPIC_QUERIES = [
    "pricing", "launch", "hiring", "deadline",
    "architecture", "migration", "deployment", "testing",
    "performance", "security",
]


def _stage_semantic_sweep(mem, since_days):
    """Stage C: Topic-based semantic queries on domain-generic themes."""
    candidates = []
    for topic in _TOPIC_QUERIES:
        results = _memory_search(mem, topic, limit=10, since_days=since_days)
        for r in results:
            entry = dict(r)
            entry["_stage"] = "semantic_sweep"
            entry["_topic"] = topic
            candidates.append(entry)
    return candidates


def _stage_filter(conn, candidates):
    """Stage D: Filter candidates against current graph state.

    Skip candidates whose information is already captured in the graph.
    """
    filtered = []
    for candidate in candidates:
        text = candidate.get("text", "")
        if not text:
            filtered.append(candidate)
            continue

        # Extract potential entity references from the text
        words = text.split()
        key_phrases = []
        # Use the first substantive phrase (up to 5 words) as a search term
        if len(words) >= 3:
            key_phrases.append(" ".join(words[:5]))

        already_captured = False
        for phrase in key_phrases:
            matches = search_nodes(conn, phrase)
            if matches:
                # Check if any match has recent content covering this
                for match in matches[:3]:
                    node = get_node(conn, match.get("n.id", match.get("id", "")))
                    if node and node.get("content") and len(node.get("content", "")) > 100:
                        already_captured = True
                        break
            if already_captured:
                break

        if not already_captured:
            filtered.append(candidate)

    return filtered


def _stage_propose(filtered):
    """Stage E: Build a JSON batch of create_node / update_node / create_edge operations."""
    proposals = []
    seen_ids = set()

    for candidate in filtered:
        text = candidate.get("text", "")
        if not text:
            continue

        # Generate a deterministic ID from the candidate text
        text_hash = hashlib.sha256(text.encode()).hexdigest()[:8]
        stage = candidate.get("_stage", "unknown")

        # If from entity_sweep, propose an update to the existing entity
        if stage == "entity_sweep" and candidate.get("_entity_id"):
            entity_id = candidate["_entity_id"]
            if entity_id not in seen_ids:
                seen_ids.add(entity_id)
                proposals.append({
                    "op": "update_node",
                    "id": entity_id,
                    "_source": text[:500],
                    "_stage": stage,
                    "_action": "review_content_update",
                })
        else:
            # Propose a new observation node for broad/semantic findings
            node_id = f"replay-{text_hash}"
            if node_id not in seen_ids:
                seen_ids.add(node_id)
                proposals.append({
                    "op": "create_node",
                    "id": node_id,
                    "type": "observation",
                    "title": text[:80],
                    "content": text[:500],
                    "_source": text[:500],
                    "_stage": stage,
                    "_keyword": candidate.get("_keyword", ""),
                    "_topic": candidate.get("_topic", ""),
                })

    return proposals


def _deduplicate(candidates):
    """Deduplicate candidates by text content hash."""
    seen = set()
    unique = []
    for c in candidates:
        text = c.get("text", "")
        h = hashlib.sha256(text.encode()).hexdigest()
        if h not in seen:
            seen.add(h)
            unique.append(c)
    return unique


def _stage_confirm_execute(conn, proposals, yes=False):
    """Stage F: Show proposals to user, confirm, execute via writer.execute_batch()."""
    if not proposals:
        return {"proposals": proposals, "executed": False, "message": "No proposals to execute"}

    if not yes:
        click.echo(f"\n{len(proposals)} proposal(s) from conversation replay:")
        for p in proposals[:20]:
            op = p.get("op", "?")
            target = p.get("id", p.get("from", "?"))
            source = p.get("_source", "")[:80]
            click.echo(f"  {op}: {target}")
            if source:
                click.echo(f"    source: {source}...")
        if len(proposals) > 20:
            click.echo(f"  ... and {len(proposals) - 20} more")
        if not click.confirm("\nApply these proposals?"):
            return {"proposals": proposals, "executed": False, "message": "User declined"}

    # Strip internal fields before executing
    clean_ops = []
    for p in proposals:
        clean = {k: v for k, v in p.items() if not k.startswith("_")}
        clean_ops.append(clean)

    from .writer import execute_batch
    results = execute_batch(conn, clean_ops)
    return {"proposals": proposals, "executed": True, "results": results}


# --- Top-level orchestrator ---

def run_replay(conn, since_days=90, yes=False, dry_run=False):
    """Run the 6-stage conversation replay pipeline."""
    mem = _require_memory()

    # Stage A: broad keyword sweep
    candidates = _stage_broad_sweep(mem, since_days)

    # Stage B: entity-specific queries
    candidates.extend(_stage_entity_sweep(mem, conn, since_days))

    # Stage C: semantic/topic sweep
    candidates.extend(_stage_semantic_sweep(mem, since_days))

    # Deduplicate candidates by conversation excerpt hash
    candidates = _deduplicate(candidates)

    # Stage D: filter against current graph state
    filtered = _stage_filter(conn, candidates)

    # Stage E: build proposals
    proposals = _stage_propose(filtered)

    if dry_run:
        return {"proposals": proposals, "executed": False}

    # Stage F: confirm and execute
    result = _stage_confirm_execute(conn, proposals, yes=yes)
    return result
