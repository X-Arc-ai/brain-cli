## Brain (Knowledge Graph)

Your project has a knowledge graph (`brain`) that stores entities, relationships,
and temporal signals. Use it to maintain structured memory across conversations.

### Before Responding (Cognitive Loop)

Before answering any substantive question:

1. **Scan**: `brain scan <topic>` -- 3-hop topology map (broad view)
2. **Assess**: Which nodes are relevant? Which have useful file_paths?
3. **Dive**: `brain context <node>` on selected nodes (deep view)
4. **Read**: Follow file_path values for narrative depth

### After Responding (Dual-Write)

If the user shared new information:
1. Update the relevant project file (if one exists)
2. `brain write` the corresponding graph update
Both in the same response. Not optional.

### Node Creation Gates

Not everything deserves a node. Test: "Will this entity have its own relationships?"
- Yes -> create a node with required edges
- No -> add the info to an existing node's content

### Required Edges by Type

| Node Type | Required Edge |
|-----------|--------------|
| goal/task | `assigned to` person + `goal for` scope |
| blocker | `affects` or `blocks` target |

### Verify vs Update

- **Status changed?** -> `brain write` with new status (updates `updated_at`, `status_since`)
- **Content changed?** -> `brain write` with new content (updates `updated_at`)
- **Confirmed still accurate?** -> `brain verify <id>` (updates `verified_at` ONLY)

Using update when you mean verify silences staleness signals.

### Signals

Run `brain signals` to see what needs attention:
- **Stale**: nodes not verified/updated in 7/14/30+ days
- **Velocity zero**: tasks/goals stuck in non-terminal status
- **Dependency changed**: upstream node updated since you last checked
- **Recently completed**: items done in last 7 days (check what they unblock)

### Semantic Verbs

Edge verbs should read as natural sentences:
- "alice --[leads]--> project-x"
- "billing-launch --[blocked by]--> api-migration"

No rigid taxonomy. Normalize obvious duplicates.

### Quick Reference

```bash
brain scan <id>              # Topology map (start here)
brain context <id>           # Deep dive on a node
brain search "<term>"        # Find nodes by keyword
brain signals                # What needs attention
brain write node --json-data '{...}'   # Create/update node
brain write edge --json-data '{...}'   # Create/update edge
brain verify <id>            # Confirm node is still accurate
brain hygiene completeness   # Check required edges
brain dream                  # Run maintenance cycle
brain viz                    # Open graph visualization
```
