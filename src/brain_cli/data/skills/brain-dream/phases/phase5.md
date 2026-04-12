# Phase 5: Execute

Apply the auto-fixable batch from Phase 4. This is the ONLY phase that writes
to brain.

## Steps

1. Read the `auto_fix` list from Phase 4 results
2. For each operation, validate:
   - Node exists (for updates): `brain get <id>`
   - Required edges present (for new nodes)
   - Not in protected_nodes list
3. Execute via `brain write batch --json-data '[...]'`
4. Verify execution: `brain hygiene completeness`

## Rules

- ONLY apply operations classified as auto_fix in Phase 4
- Do NOT apply anything from needs_human
- If validation fails for any operation, skip it and add to error list
- Run `brain hygiene completeness` after the batch to verify no new violations

## Output Format

Respond with JSON only:

```json
{
  "applied": 8,
  "skipped": 2,
  "errors": [],
  "post_hygiene_clean": true
}
```
