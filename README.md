<p align="center">
  <img src="assets/hero.svg" alt="brain" width="700">
</p>

<p align="center">
  <strong>Give your AI coding agent a knowledge graph that compounds.</strong><br>
  Entities, relationships, signals. All local. Zero config.
</p>

---

## Quick Start

```bash
pip install git+https://github.com/X-Arc-ai/brain-cli.git
cd your-project
brain init
```

That's it. Your agent maintains the graph automatically.

---

## How It Works

Every conversation follows a cognitive loop:

1. **Scan** -- query the graph for context before responding
2. **Respond** -- with full awareness of entities, relationships, and history
3. **Write** -- capture new information back to the graph

This loop is enforced by hooks that fire automatically. You don't need to
remember to use the brain. It's architecturally guaranteed.

<p align="center">
  <img src="assets/demo-scan.svg" alt="brain scan" width="640">
</p>

---

## What It Tracks

Brain stores **entities** (projects, people, goals, tasks, blockers, decisions, events),
**relationships** between them (who owns what, what blocks what, what depends on what),
and **temporal signals** (what's stale, what's stuck, what just shipped).

<p align="center">
  <img src="assets/demo-signals.svg" alt="brain signals" width="640">
</p>

---

## What It Looks Like in Production

This is the actual brain of CCL, the AI agent that built this tool.
320 nodes, 975 edges, 6 months of compounding memory across multiple
companies, projects, and people.

<p align="center">
  <img src="assets/brain-production.png" alt="CCL's production brain -- 320 nodes, 975 edges" width="800">
</p>

<p align="center">
  <em>Your agent builds this over time. Every conversation adds to the graph.</em>
</p>

---

## Type System

Nodes are organized in three tiers:

| Tier | Purpose | Default Types |
|------|---------|---------------|
| **Structural** | Long-lived entities | `project`, `person` |
| **Operational** | Active work items | `goal`, `task`, `decision`, `blocker` |
| **Temporal** | Immutable records | `event`, `observation`, `status_change` |

Add your own types:

```bash
brain config add-type service structural
brain config add-type feature operational
```

---

## Signals

`brain signals` computes what needs attention:

| Signal | What It Detects |
|--------|-----------------|
| **Stale** | Nodes not verified/updated in 7/14/30+ days |
| **Velocity zero** | Tasks/goals stuck in non-terminal status |
| **Dependency changed** | Upstream node updated since you last checked |
| **Recently completed** | Items done in last 7 days (check what they unblock) |
| **Recurring overdue** | Recurring activities past their frequency threshold |

---

## CLI Reference

```
brain init                           Bootstrap graph from your project
brain scan <id>                      3-hop topology map (start here)
brain context <id>                   Deep dive on a node + neighbors
brain search "<term>"                Find nodes by keyword
brain search-semantic "<query>"      Find nodes by meaning (requires OpenAI)
brain signals                        What needs attention
brain stats                          Graph statistics
brain write node --json-data '{}'    Create or update a node
brain write edge --json-data '{}'    Create or update an edge
brain write batch --json-data '[]'   Batch operations
brain verify <id>                    Confirm node is still accurate
brain dream                          Run maintenance cycle
brain hygiene completeness           Check required edges
brain config show                    Current configuration
brain viz                            Open graph visualization
brain export --format batch          Backup (replayable)
```

---

## Optional Features

### Semantic Search

```bash
pip install 'brain-cli[embeddings]'
# Set OPENAI_API_KEY in your environment
brain embed backfill
brain search-semantic "authentication flow"
```

### Conversation History Replay

```bash
pip install 'brain-cli[memory]'
# brain dream will index and replay past conversations
```

---

## Architecture

```
your-project/
  .brain/              Brain data (add to .gitignore)
    db/                Kuzu embedded graph database
    exports/           Visualization data
    viz/               Cytoscape.js graph visualization
    hooks/             Enforcement hooks (stable across upgrades)
    config.json        Type tiers, custom settings
  .claude/
    settings.local.json   Hooks (auto-installed by brain init)
  CLAUDE.md            Brain instructions (auto-installed)
```

---

## How It's Built

- [Kuzu](https://kuzudb.com/) -- embedded graph database, no server
- [Rich](https://github.com/Textualize/rich) -- terminal formatting
- [Click](https://click.palletsprojects.com/) -- CLI framework
- [Cytoscape.js](https://js.cytoscape.org/) -- graph visualization (bundled offline)

~3,500 lines of Python. Fully auditable. No magic.

**Nothing leaves your machine.** No cloud services. No telemetry. The only
optional external call is OpenAI for semantic search embeddings, and that's
opt-in via `pip install 'brain-cli[embeddings]'`.

---

## Roadmap

**v0.1 (current):** Core engine, Rich TUI, visualization, hooks, brain init, brain dream

**Next:**
- Graph diff (what changed since last session)
- Auto-dream on session boundaries (Claude Code Stop hook)
- Multi-agent graph sharing
- MCP server for native tool integration

Contributions welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## How This Was Built

This project was built by CCL, an AI agent deployed on [X-Arc](https://x-arc.ai)'s
CCX platform. CCL manages operations, builds tools, and ships code across
multiple projects. You can see CCL as a contributor on this repo.

Brain started as CCL's internal memory system. After 6 months of daily use
(320 nodes, 975 edges, 5 signal types, 7 hygiene checks running nightly),
CCL packaged and open-sourced it.

X-Arc deploys AI agents that ship real work. Manage it like a hire. It works like ten.

[x-arc.ai](https://x-arc.ai) | [GitHub](https://github.com/x-arc-ai)
