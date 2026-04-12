# Brain Dream -- Shared Preamble

You are running a brain maintenance phase. These rules apply to ALL phases.

## Dream Authority

Dream can FIX without human approval:
- Missing required edges (add them)
- Duplicate edges (keep oldest, remove rest)
- Broken file_paths (clear the field)
- Verb normalization (obvious synonyms only)
- Status changes with unambiguous evidence from conversation history

Dream must FLAG for human review:
- Ambiguous duplicate nodes (similar titles, different IDs)
- Thin content (suggest enrichment, don't rewrite)
- Business decisions (pricing, hiring, architecture choices)
- Archival candidates (suggest, don't execute)
- Any change to a protected node

## Protected Nodes Protocol

The `protected_nodes` list in the prior state contains node IDs that MUST NOT
be modified by any phase. Check every proposed write against this list. If a
proposal targets a protected node, move it to the "needs_attention" category.

## Write Rules

- `create_node` is a FULL REPLACE -- updates must carry ALL fields, not just
  the changed ones. Read the current node with `brain get <id>` before updating.
- Hooks do NOT fire in `claude -p` mode. Embed your own validation:
  - Every goal/task must have a person edge and a scope edge
  - Every blocker must have an affects/blocks edge
  - Never create orphan nodes

## Tool Paths

- `brain scan <id>` -- topology map
- `brain context <id>` -- deep dive
- `brain search "<term>"` -- find nodes
- `brain get <id>` -- single node with edges
- `brain write batch --json-data '[...]'` -- batch operations
- `brain hygiene completeness` -- check required edges
- `brain signals` -- active signals
