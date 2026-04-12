## Brain (Knowledge Graph)

Your project has a knowledge graph (`brain`) that stores entities, relationships,
and temporal signals. Use it to maintain structured memory across conversations.

### Before Responding (Cognitive Loop)

Before answering any substantive question:

1. **Scan**: `brain scan <topic>` -- 3-hop topology map (broad view)
2. **Assess**: Which nodes are relevant? Which have useful file_paths?
3. **Dive**: `brain context <node>` on selected nodes (deep view)
4. **Read**: Follow file_path values for narrative depth

### Scan Layers

`brain scan <id>` returns three-hop topology with progressive detail:
- Root + hop 1: full content and properties (the first answer layer)
- Hop 2+: lightweight metadata (id, type, title, status, file_path)

Scanning is the MAP. It tells you what exists and how it's connected. It does
NOT give you the narrative -- that comes from `brain context` on specific nodes
+ reading their `file_path` files. The loop is:

  scan (the map) -> assess (what matters) -> dive (the room) -> extend (if the
  scan boundary hid something important)

Never answer from a 1-hop keyhole view. Never answer from scan metadata alone
for structural nodes -- a company or person node always gets a dive on
assessment.

### Dive = Brain + File + Live Sources

A dive is not just brain data. For each node type, the dive includes whatever
live sources exist in your environment:

| Node Type | Brain Dive | Live Source Dive (same step) |
|---|---|---|
| company/project | `brain context` + read file_path + roadmap siblings | code host (PRs, commits), chat (channels) |
| person | `brain context` + read file_path | code host (commits), chat (messages) |
| goal/task | `brain context` + edge traversal | PRs/branches if code-related |
| blocker | `brain context` + edge traversal | verify blocking condition via any live source |

If the environment has a calendar, ticketing system, deployment tool, or chat
integration, include those when diving on relevant nodes. brain-cli does not
ship these integrations -- the user wires their own. But the cognitive contract
assumes the dive reaches beyond the graph.

### After Responding (Dual-Write)

If the user shared new information:
1. Update the relevant project file (if one exists)
2. `brain write` the corresponding graph update
Both in the same response. Not optional.

### Structural Propagation

When a structural change happens (new repo, person leaves, priority shifts),
multiple nodes need updating in one operation. The dual-write rule says
"write what changed" -- structural propagation says "write the ripples too."

Examples of structural changes and their ripples:
- Person leaves -> end role edges, reassign tasks, update team content
- Project archived -> cascade status to child goals/tasks
- Priority shift -> update status_since on affected goals, check blockers

Use `brain write batch` for multi-node structural updates.

### Node Creation Gates

Not everything deserves a node. Test: "Will this entity have its own
relationships?"
- Yes -> create a node with required edges
- No -> add the info to the nearest existing node's content

**Blocker gate:** only create a blocker node if it concretely prevents a
specific deliverable from shipping. External stakeholder decisions, commercial
discussions, and "we're waiting on someone else" are information on existing
nodes -- not separate blocker nodes. Noise blockers trigger false
velocity-zero signals.

**Own-deliverable gate:** only create goal/task nodes for items YOU or your
team can act on. Other parties' action items go in content on the relevant
existing node.

### Required Edges by Node Type (extended)

| Node Type | Required Edge(s) |
|---|---|
| goal / task | `assigned to` or `owned by` -> person AND `goal for` / `task of` -> scope (project/product/company) |
| blocker | `affects` / `blocks` -> target AND (if known) `owned by` -> person |
| product | `product of` -> company/project |
| client | `client of` or `potential client of` -> company |
| person | at least one role edge to a company/project (`leads`, `works on`, `contributes to`, `founded`) |
| instance | `deployed to serve` -> company/project AND `managed by` -> person |

Run `brain hygiene completeness` after any batch write to verify.

### Temporal Field Semantics

| Field | Meaning | Updated When | Used By |
|---|---|---|---|
| `updated_at` | Content or status last changed | Real changes: status, content, title | Staleness detection |
| `verified_at` | Human confirmed it's still accurate | `brain verify` only | Staleness (secondary), dependency freshness |
| `status_since` | When current status was set | Status changes only | Velocity-zero detection |

**Critical rule: "I looked at it" != "progress was made."**
- Status changed? -> `brain write` with new status
- Content genuinely changed? -> `brain write` with new content
- Confirmed still accurate (no real change)? -> `brain verify <id>` (touches
  verified_at ONLY)

Using `update_node` to annotate "still blocked, 20 days" resets updated_at
and silences the staleness signal. That's the wrong operation.

### Properties vs Content

- **content** -- markdown prose. Human-readable. The first answer layer when
  someone queries the node.
- **properties** -- JSON. Machine-readable. For deadlines, URLs, contact
  handles, amounts, versions, flags.

Examples:

| Use case | Properties |
|---|---|
| Deadline | `{"deadline": "2026-06-30", "deadline_label": "Quarter end"}` |
| Pricing | `{"amount": 400, "currency": "USD", "period": "monthly"}` |
| Contact | `{"github": ["handle1"], "slack_id": "U123ABC"}` |
| Recurring | `{"recurring": true, "frequency": "weekly"}` |

Properties supplement content. They do not replace it.

### Where file_path Points

brain tracks entities but doesn't store their narrative. The narrative lives
in markdown files that `file_path` points to.

Default convention (you can override):
  context/companies/{company-id}/overview.md
  context/projects/{project-id}/overview.md
  context/people/{person-id}.md
  context/products/{product-id}.md

A structural node's content field is the "first answer layer" -- enough to
answer operational questions at a glance. The file at file_path is the deep
narrative -- history, full context, anything that would bloat the graph.

When you follow a file_path, also check the directory for siblings -- a
project's overview.md usually sits next to a roadmap.md and a backlog.md.

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
brain write batch --json-data '[...]'  # Batch operations
brain verify <id>            # Confirm node is still accurate
brain hygiene completeness   # Check required edges
brain hygiene dedup-edges    # Find duplicate edges
brain replay --dry-run       # Mine conversations for graph updates
brain dream                  # Run maintenance cycle
brain viz                    # Open graph visualization
```
