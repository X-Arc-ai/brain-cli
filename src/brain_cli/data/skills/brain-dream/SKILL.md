---
name: brain-dream
description: Brain maintenance -- replay conversations, fix graph quality, surface signals
context: fork
---

# Brain Dream

Run graph maintenance. Triggered automatically on session boundaries or manually via `brain dream`.

## Phases

### Phase 1: Ingest
If agent-memory is available, index new conversations:
```bash
memory ingest 2>/dev/null || true
```

### Phase 2: Hygiene
Run all quality checks:
```bash
brain hygiene dedup
brain hygiene orphans
brain hygiene completeness
brain hygiene file-paths
brain hygiene verbs
brain hygiene readiness
```

Collect all violations into a fix list.

### Phase 3: Fix
For deterministic issues (missing edges, broken file_paths, verb duplicates):
- Propose fixes as a brain write batch
- Execute the batch

For judgment calls (potential duplicates, thin content):
- Add to "Needs Attention" list for the user

### Phase 4: Signal
Compute and display signals:
```bash
brain signals
```

### Phase 5: Report
Output a summary:
- Issues found and fixed
- Items needing attention
- Active signals
- Graph stats (node/edge counts, embedding coverage)

## Rules
- NEVER modify project code files
- ONLY modify brain database and memory files
- Be conservative -- when in doubt, flag for attention instead of fixing
- Skip nodes updated in the last 24 hours
