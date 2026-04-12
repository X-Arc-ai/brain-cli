# Phase 3: Structural Audit

For each node type with live sources available in the environment, audit
freshness. This phase is SKIPPED if no live sources are wired up.

## Checks by Node Type

| Node Type | Live Source | Audit |
|---|---|---|
| project | git log, code host | Recent commits vs last brain update |
| person | git log (commits) | Activity vs claimed work items |
| goal/task | PRs/branches | Code-related items with merged PRs still "in_progress" |

## Steps

1. Check which live sources are available (git, code host APIs, etc.)
2. For each available source, query recent activity
3. Compare against brain node timestamps (updated_at, verified_at)
4. Flag nodes where live source shows activity but brain is stale

If NO live sources are available, output an empty result and move on.

## Output Format

Respond with JSON only:

```json
{
  "sources_checked": ["git"],
  "audit_findings": [
    {"node_id": "...", "finding": "...", "source": "git", "action": "update/verify"}
  ]
}
```
