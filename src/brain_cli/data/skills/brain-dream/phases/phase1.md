# Phase 1: Hygiene

Run all `brain hygiene` checks. Collect violations into categorized lists.

## Steps

1. Run each hygiene check:
   - `brain hygiene dedup` (duplicate nodes)
   - `brain hygiene orphans` (disconnected nodes)
   - `brain hygiene completeness` (missing required edges)
   - `brain hygiene file-paths` (broken/missing file_path)
   - `brain hygiene content-drift` (brain vs file divergence)
   - `brain hygiene verbs` (verb audit)
   - `brain hygiene readiness` (operational readiness)
   - `brain hygiene dedup-edges` (duplicate edges)

2. Categorize each violation as:
   - **fixable**: dream can resolve automatically (see preamble authority)
   - **needs_attention**: requires human review

## Output Format

Respond with JSON only:

```json
{
  "violations": [...],
  "fixable": [...],
  "needs_attention": [...]
}
```
