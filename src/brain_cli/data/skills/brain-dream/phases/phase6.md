# Phase 6: Report

Generate the final dream report. Summarize what was found, fixed, and flagged.

## Steps

1. Read all prior phase results
2. Compute summary statistics
3. Write the report to stdout as JSON

## Report Contents

- **hygiene**: issues found vs fixed (from phases 1 + 5)
- **replay**: candidates found, already captured, proposals made (from phase 2)
- **audit**: sources checked, findings (from phase 3)
- **execution**: operations applied, skipped, errors (from phase 5)
- **human_review**: items that need human attention (from phase 4)
- **graph_stats**: run `brain stats` for current counts

## Output Format

Respond with JSON only:

```json
{
  "summary": {
    "issues_found": 12,
    "issues_fixed": 8,
    "signals_active": 3,
    "graph_nodes": 45,
    "graph_edges": 78
  },
  "human_review": [...],
  "details": {
    "hygiene": {...},
    "replay": {...},
    "audit": {...},
    "execution": {...}
  }
}
```
