# Contributing to Brain

## Extension Points

Brain is designed to be extended. Here's where to add your own customizations.

### Custom Node Types

Register new types in any of the three tiers:

```bash
brain config add-type service structural
brain config add-type feature operational
brain config add-type milestone temporal
```

Or edit `.brain/config.json` directly:

```json
{
  "type_tiers": {
    "structural": ["service", "team", "repository"],
    "operational": ["feature", "bug", "spike"]
  }
}
```

### Custom Hygiene Rules

The edge completeness rules in `hygiene.py` define what edges each node type requires. To add rules for your custom types, extend `EDGE_RULES`:

```python
EDGE_RULES.append({
    "node_type": "feature",
    "check": "outgoing",
    "target_types": ["person"],
    "verbs": ["assigned to", "owned by"],
    "description": "Every feature must have an owner",
})
```

### Custom Hooks

Brain ships with 4 hooks. You can add your own by editing `.claude/settings.local.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "type": "command",
        "command": "bash .brain/hooks/my-custom-hook.sh",
        "timeout": 10000,
        "matcher": "Bash"
      }
    ]
  }
}
```

### Custom Signal Types

Signals are computed in `signals.py`. Each signal is a function that queries the graph and returns a list of items needing attention. Add your own by following the pattern of existing `compute_*` functions.

## Development Setup

```bash
git clone https://github.com/X-Arc-ai/brain-cli.git
cd brain-cli
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

## Running Tests

```bash
pytest tests/ -v                    # All tests
pytest tests/test_writer.py -v      # Single module
pytest tests/ --cov=brain_cli       # With coverage
```

All tests use an isolated temp database. No external services needed.

## Code Structure

```
src/brain_cli/
  cli.py          # Click CLI (all commands)
  config.py       # Paths, type system, constants
  database.py     # Kuzu connection factory
  schema.py       # DDL + migrations
  writer.py       # Node/edge CRUD
  reader.py       # Scan, context, search, queries
  signals.py      # 5 signal computations
  hygiene.py      # 7 quality checks
  exporter.py     # Cytoscape, JSON, batch export
  embeddings.py   # OpenAI embeddings (optional)
  tui.py          # Rich-based output formatting
  init.py         # brain init onboarding
  utils.py        # Shared helpers
```

## Pull Requests

1. Fork the repo
2. Create a feature branch
3. Write tests for new functionality
4. Run `pytest tests/ -v` and ensure all pass
5. Submit PR with a clear description

## License

Apache 2.0. By contributing, you agree your contributions will be licensed under the same terms.
