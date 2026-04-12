# Phase 2: Conversation Replay

Mine the indexed conversation store for information the interactive dual-write
missed. This is the phase that keeps the graph honest.

## Strategy: 4 rounds with minimum query count

### Round 1 -- Broad Keyword Sweep
Query the conversation store for signal keywords:
  "decision", "shipped", "blocked", "changed", "new", "FYI", "update", "correction"
Minimum 8 queries (one per keyword). Limit 20 results each.

### Round 2 -- Per-Entity Queries
For every structural node in the graph (project, person, company, product),
query the conversation store by title and key properties.
Run `brain search` with type filters to get the entity list first.
Minimum: one query per structural node. Limit 10 results each.

### Round 3 -- Topic-Based Semantic
Query for domain-generic themes active in the period:
  "pricing", "launch", "hiring", "deadline", "architecture", "migration"
Minimum 6 queries. Limit 10 results each.

### Round 4 -- Gap Assessment
For each priority entity with zero hits in Rounds 1-3, run 3 additional
targeted searches using alternative phrasings or abbreviations.

## Intelligence Filter

For each finding from any round:
1. `brain search "<key phrase>"` -- does the graph already know this?
2. `brain get <id>` if a match is found -- is the captured info current?
3. SKIP if already captured and current. PROPOSE if stale or missing.

## Output Format

Respond with JSON only:

```json
{
  "candidates_found": 42,
  "already_captured": 30,
  "proposed_operations": [
    {"op": "create_node", "id": "...", "type": "...", "title": "...", "_source": "..."},
    {"op": "update_node", "id": "...", "content": "...", "_source": "..."},
    {"op": "create_edge", "from": "...", "to": "...", "verb": "...", "_source": "..."}
  ]
}
```
