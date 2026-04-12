# Phase 4: Assessment

Consolidate proposals from phases 1-3. Split into auto-fixable vs needs-human.

## Steps

1. Read the prior phase state (phases 1, 2, 3 results)
2. Merge all proposed operations into a single list
3. For each proposal, classify:
   - **auto_fix**: dream has authority to apply (see preamble)
   - **needs_human**: ambiguous, business-sensitive, or touches protected nodes
4. Check every proposal against the protected_nodes list
5. Deduplicate proposals targeting the same node

## Output Format

Respond with JSON only:

```json
{
  "total_proposals": 15,
  "auto_fix": [
    {"op": "...", "id": "...", "reason": "..."}
  ],
  "needs_human": [
    {"op": "...", "id": "...", "reason": "...", "category": "ambiguous|business|protected"}
  ]
}
```
