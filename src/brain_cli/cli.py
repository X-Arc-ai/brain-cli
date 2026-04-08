"""Brain -- Knowledge Graph CLI for structured memory."""

import json
import sys

import click
from dotenv import load_dotenv

load_dotenv()

from . import __version__
from .database import get_connection
from .writer import create_node, update_node, archive_node, create_edge, update_edge, end_edge, execute_batch
from .reader import (get_node, get_context, scan_subgraph, query_cypher, query_depends_on,
                     query_blast_radius, query_chain, query_changed_since, query_stale,
                     query_person, search_nodes, search_semantic, get_all_nodes_for_embedding, get_stats)
from .signals import compute_all_signals
from .hygiene import (find_duplicates, find_orphans, audit_verbs, check_completeness,
                      check_operational_readiness, check_file_paths, check_content_drift)
from .exporter import export_cytoscape, export_json, export_batch


def _handle_errors(fn):
    """Decorator: convert ValueError/JSONDecodeError to clean CLI errors."""
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except json.JSONDecodeError as e:
            raise click.ClickException(f"Invalid JSON: {e}")
        except ValueError as e:
            raise click.ClickException(str(e))

    return wrapper


def _output(data):
    """Print JSON output."""
    click.echo(json.dumps(data, indent=2, default=str))


def _auto_export():
    """Auto-export graph after writes so viz stays in sync."""
    try:
        export_conn = get_connection(max_retries=1, base_delay=0)
        export_cytoscape(export_conn)
        export_batch(export_conn)
    except Exception as e:
        click.echo(f"Warning: auto-export failed: {e}", err=True)


@click.group()
@click.version_option(version=__version__, prog_name="brain")
@click.option("--json-output", "json_mode", is_flag=True, help="Output raw JSON instead of formatted text")
@click.pass_context
def cli(ctx, json_mode):
    """Brain -- Knowledge Graph CLI for structured memory."""
    ctx.ensure_object(dict)
    ctx.obj["json_mode"] = json_mode


# --- Init ---

@cli.command("init")
@click.option("--project", type=click.Path(exists=True), help="Project root directory")
@click.option("--skip-memory", is_flag=True, help="Skip conversation history indexing")
@click.option("--skip-hooks", is_flag=True, help="Skip Claude Code hook installation")
@click.option("--skip-viz", is_flag=True, help="Skip opening visualization")
@click.option("--yes", "-y", is_flag=True, help="Auto-confirm all prompts (non-interactive)")
def init_cmd(project, skip_memory, skip_hooks, skip_viz, yes):
    """Initialize brain for a project. Analyzes codebase, proposes graph, installs hooks."""
    from .init import run_init
    run_init(
        project_root=project,
        skip_memory=skip_memory,
        skip_hooks=skip_hooks,
        skip_viz=skip_viz,
        yes=yes,
    )


# --- Write ---

@cli.group()
def write():
    """Write nodes and edges to the graph."""
    pass


@write.command("node")
@click.option("--json-data", "json_str", required=True, help="Node data as JSON string")
@click.option("--maintenance", is_flag=True, help="Allow status+properties updates on immutable types")
@_handle_errors
def write_node(json_str, maintenance):
    """Create or update a node."""
    data = json.loads(json_str)
    conn = get_connection()
    if data.get("op") == "update_node":
        update_node(conn, data, maintenance=maintenance)
        click.echo(f"Updated node: {data['id']}")
    else:
        create_node(conn, data)
        click.echo(f"Created node: {data['id']}")
    _auto_export()


@write.command("edge")
@click.option("--json-data", "json_str", required=True, help="Edge data as JSON string")
@_handle_errors
def write_edge(json_str):
    """Create or update an edge."""
    data = json.loads(json_str)
    conn = get_connection()
    if data.get("op") == "update_edge":
        update_edge(conn, data)
        click.echo(f"Updated edge: {data['from']} --[{data['verb']}]--> {data['to']}")
    else:
        create_edge(conn, data)
        click.echo(f"Created edge: {data['from']} --[{data['verb']}]--> {data['to']}")
    _auto_export()


@write.command("batch")
@click.option("--json-data", "json_str", default=None, help="Batch operations as JSON array string")
@click.option("--file", "file_path", default=None, type=click.Path(exists=True), help="Batch operations from JSON file")
@_handle_errors
def write_batch(json_str, file_path):
    """Execute a batch of operations."""
    if file_path:
        with open(file_path) as f:
            operations = json.load(f)
    elif json_str:
        operations = json.loads(json_str)
    else:
        operations = json.load(sys.stdin)

    if not isinstance(operations, list):
        raise click.ClickException("Batch must be a JSON array of operations")

    conn = get_connection()
    results = execute_batch(conn, operations)
    click.echo(f"Batch complete: {len(results)} operations executed.")
    _output(results)
    _auto_export()


# --- Delete ---

@cli.group()
def delete():
    """Delete (archive) nodes and end edges."""
    pass


@delete.command("node")
@click.option("--id", "node_id", required=True, help="Node ID to archive")
@_handle_errors
def delete_node(node_id):
    """Soft-delete a node (set status to archived)."""
    conn = get_connection()
    archive_node(conn, node_id)
    click.echo(f"Archived node: {node_id}")
    _auto_export()


@delete.command("edge")
@click.option("--from", "from_id", required=True, help="Source node ID")
@click.option("--to", "to_id", required=True, help="Target node ID")
@click.option("--verb", required=True, help="Relationship verb")
@_handle_errors
def delete_edge_cmd(from_id, to_id, verb):
    """End a relationship (set until = now)."""
    conn = get_connection()
    end_edge(conn, from_id, to_id, verb)
    click.echo(f"Ended edge: {from_id} --[{verb}]--> {to_id}")
    _auto_export()


# --- Get ---

@cli.command()
@click.argument("node_id")
@click.pass_context
def get(ctx, node_id):
    """Get a node by ID with all its edges."""
    conn = get_connection()
    node = get_node(conn, node_id)
    if node is None:
        click.echo(f"Node not found: {node_id}", err=True)
        sys.exit(1)
    if ctx.obj.get("json_mode"):
        _output(node)
    else:
        from .tui import format_node
        format_node(node)


# --- Scan ---

@cli.command()
@click.argument("node_id")
@click.option("--depth", default=3, help="Hop depth (default: 3)")
@click.pass_context
def scan(ctx, node_id, depth):
    """Layer 1: Topology scan with progressive detail (3-hop)."""
    conn = get_connection()
    result = scan_subgraph(conn, node_id, depth)
    if result is None:
        click.echo(f"Node not found: {node_id}", err=True)
        sys.exit(1)
    if ctx.obj.get("json_mode"):
        _output(result)
    else:
        from .tui import format_scan
        format_scan(result)


# --- Context ---

@cli.command()
@click.argument("node_id")
@click.option("--depth", default=1, help="Hop depth (default: 1)")
@click.pass_context
def context(ctx, node_id, depth):
    """Layer 2: Deep dive with full content."""
    conn = get_connection()
    result = get_context(conn, node_id, depth)
    if result is None:
        click.echo(f"Node not found: {node_id}", err=True)
        sys.exit(1)
    if ctx.obj.get("json_mode"):
        _output(result)
    else:
        from .tui import format_context
        format_context(result)


# --- Search ---

@cli.command()
@click.argument("query_str")
@click.option("--type", "type_filter", default=None, help="Filter by node type")
@click.pass_context
def search(ctx, query_str, type_filter):
    """Search all nodes by title, content, or ID."""
    conn = get_connection()
    results = search_nodes(conn, query_str, type_filter)
    if not results:
        click.echo(f"No nodes matching: {query_str}")
    elif ctx.obj.get("json_mode"):
        _output(results)
    else:
        from .tui import format_search
        format_search(results)


# --- Search Semantic ---

@cli.command("search-semantic")
@click.argument("query_str")
@click.option("--type", "type_filter", default=None, help="Filter by node type")
@click.option("--top-k", default=10, help="Number of results (default 10)")
@click.option("--expand", is_flag=True, help="Include 1-hop connections per result")
@click.pass_context
def search_semantic_cmd(ctx, query_str, type_filter, top_k, expand):
    """Semantic search using embedding similarity."""
    conn = get_connection()
    results = search_semantic(conn, query_str, type_filter=type_filter, top_k=top_k, expand=expand)
    _output(results)


# --- Query ---

@cli.group()
def query():
    """Query the knowledge graph."""
    pass


_DESTRUCTIVE_KEYWORDS = (
    "DELETE", "DETACH", "SET", "CREATE", "MERGE", "REMOVE", "DROP", "ALTER",
)


def _looks_destructive(query_text: str) -> bool:
    """Heuristic check: does the query contain a destructive keyword?

    This is a defensive guard, not a security boundary. Treats unquoted
    keyword tokens (whitespace-bounded) as destructive. Users determined
    to evade this can do so trivially. Real safety comes from the LLM-facing
    surface (the brain skill) not invoking destructive Cypher.
    """
    upper = query_text.upper()
    padded = f" {upper} "
    for kw in _DESTRUCTIVE_KEYWORDS:
        if f" {kw} " in padded:
            return True
        if upper.startswith(f"{kw} "):
            return True
    return False


@query.command("cypher")
@click.argument("cypher_query")
@click.option(
    "--read-only",
    is_flag=True,
    help="Reject queries containing DELETE/SET/CREATE/MERGE/REMOVE/etc.",
)
def query_cypher_cmd(cypher_query, read_only):
    """Execute a raw Cypher query.

    \b
    WARNING: This bypasses brain's schema validation and can permanently
    modify or delete data. Use --read-only to reject destructive keywords.
    Prefer the typed `brain write` and `brain query` commands when possible.
    """
    if read_only and _looks_destructive(cypher_query):
        click.echo(
            "Error: --read-only mode rejected query containing a destructive keyword "
            f"(one of {', '.join(_DESTRUCTIVE_KEYWORDS)}).",
            err=True,
        )
        sys.exit(2)
    conn = get_connection()
    results = query_cypher(conn, cypher_query)
    _output(results)


@query.command("depends-on")
@click.argument("node_id")
def query_depends_on_cmd(node_id):
    """What depends on this node?"""
    conn = get_connection()
    results = query_depends_on(conn, node_id)
    _output(results)


@query.command("blast-radius")
@click.argument("node_id")
@click.option("--hops", default=3, help="Number of hops (default: 3)")
def query_blast_radius_cmd(node_id, hops):
    """N-hop affected subgraph from a node."""
    conn = get_connection()
    results = query_blast_radius(conn, node_id, hops)
    _output(results)


@query.command("chain")
@click.argument("node_id")
def query_chain_cmd(node_id):
    """Full dependency chain."""
    conn = get_connection()
    results = query_chain(conn, node_id)
    _output(results)


@query.command("changed-since")
@click.argument("date")
def query_changed_since_cmd(date):
    """Nodes updated after a given date (YYYY-MM-DD)."""
    conn = get_connection()
    results = query_changed_since(conn, date)
    _output(results)


@query.command("stale")
@click.option("--threshold", default=14, help="Days threshold (default: 14)")
def query_stale_cmd(threshold):
    """Nodes with freshness > threshold days."""
    conn = get_connection()
    results = query_stale(conn, threshold)
    _output(results)


@query.command("person")
@click.argument("person_id")
def query_person_cmd(person_id):
    """Full person assessment subgraph."""
    conn = get_connection()
    results = query_person(conn, person_id)
    _output(results)


# --- Signals ---

@cli.command()
@click.pass_context
def signals(ctx):
    """Compute and display all active signals."""
    conn = get_connection()
    results = compute_all_signals(conn)
    if ctx.obj.get("json_mode"):
        _output(results)
    else:
        from .tui import format_signals
        format_signals(results)


# --- Stats ---

@cli.command()
@click.pass_context
def stats(ctx):
    """Show node/edge counts by type."""
    conn = get_connection()
    results = get_stats(conn)
    if ctx.obj.get("json_mode"):
        _output(results)
    else:
        from .tui import format_stats
        format_stats(results)


# --- Export ---

@cli.command("export")
@click.option("--format", "fmt", default="cytoscape", type=click.Choice(["cytoscape", "json", "batch"]))
def export_cmd(fmt):
    """Export graph for visualization or backup."""
    conn = get_connection()
    if fmt == "cytoscape":
        path, nodes, edges = export_cytoscape(conn)
        click.echo(f"Exported {nodes} nodes, {edges} edges to {path}")
    elif fmt == "batch":
        path, nodes, edges = export_batch(conn)
        click.echo(f"Backup: {nodes} nodes, {edges} edges to {path}")
        click.echo(f"Recover with: brain write batch --file {path}")
    else:
        path = export_json(conn)
        click.echo(f"Exported to {path}")


# --- Embed ---

@cli.group()
def embed():
    """Embedding management commands."""
    pass


@embed.command("backfill")
@click.option("--force", is_flag=True, help="Re-embed nodes that already have embeddings")
def embed_backfill(force):
    """Generate embeddings for all nodes."""
    from .embeddings import generate_embeddings_batch, node_text_for_embedding, EMBEDDING_DIMS

    conn = get_connection()

    nodes = get_all_nodes_for_embedding(conn)
    if not force:
        nodes = [n for n in nodes if not n.get("has_embedding")]

    embedded_count = 0
    if nodes:
        click.echo(f"Embedding {len(nodes)} nodes...")
        texts = [node_text_for_embedding({"title": n["n.title"], "content": n["n.content"]}) for n in nodes]
        embeddings = generate_embeddings_batch(texts)
        for node, emb in zip(nodes, embeddings):
            conn.execute(
                "MATCH (n:Node {id: $id}) SET n.content_embedding = $emb",
                parameters={"id": node["n.id"], "emb": emb}
            )
        embedded_count = len(nodes)
    else:
        click.echo("All active nodes already have embeddings.")

    zero_vec = [0.0] * EMBEDDING_DIMS
    null_result = conn.execute(
        "MATCH (n:Node) WHERE n.content_embedding IS NULL RETURN n.id"
    )
    null_cols = null_result.get_column_names()
    null_count = 0
    while null_result.has_next():
        row = dict(zip(null_cols, null_result.get_next()))
        conn.execute(
            "MATCH (n:Node {id: $id}) SET n.content_embedding = $emb",
            parameters={"id": row["n.id"], "emb": zero_vec}
        )
        null_count += 1
    if null_count:
        click.echo(f"Filled {null_count} archived/skipped nodes with zero vectors.")

    _auto_export()

    _output({
        "status": "ok",
        "embedded": embedded_count,
        "zero_filled": null_count,
        "dimensions": EMBEDDING_DIMS
    })


@embed.command("status")
def embed_status():
    """Show embedding coverage statistics."""
    conn = get_connection()

    result = conn.execute(
        "MATCH (n:Node) "
        "RETURN "
        "  count(n) AS total, "
        "  count(CASE WHEN n.content_embedding IS NOT NULL THEN 1 END) AS embedded, "
        "  count(CASE WHEN n.status = 'archived' THEN 1 END) AS archived"
    )
    rows = []
    cols = result.get_column_names()
    while result.has_next():
        rows.append(dict(zip(cols, result.get_next())))
    row = rows[0] if rows else {}

    _output({
        "total_nodes": row.get("total", 0),
        "embedded": row.get("embedded", 0),
        "archived": row.get("archived", 0),
        "coverage": f"{(row.get('embedded', 0) / max(row.get('total', 1), 1) * 100):.1f}%"
    })


# --- Hygiene ---

@cli.group()
def hygiene():
    """Graph maintenance and quality checks."""
    pass


@hygiene.command("dedup")
@click.pass_context
def hygiene_dedup(ctx):
    """Find potential duplicate nodes."""
    conn = get_connection()
    results = find_duplicates(conn)
    if not results:
        click.echo("No duplicates found.")
    elif ctx.obj.get("json_mode"):
        _output(results)
    else:
        from .tui import format_hygiene
        format_hygiene("duplicates", results)


@hygiene.command("orphans")
@click.pass_context
def hygiene_orphans(ctx):
    """Find disconnected nodes (no edges)."""
    conn = get_connection()
    results = find_orphans(conn)
    if not results:
        click.echo("No orphan nodes found.")
    elif ctx.obj.get("json_mode"):
        _output(results)
    else:
        from .tui import format_hygiene
        format_hygiene("orphans", results)


@hygiene.command("verbs")
def hygiene_verbs():
    """List all relationship verbs with counts."""
    conn = get_connection()
    results = audit_verbs(conn)
    if not results:
        click.echo("No edges in the graph.")
    else:
        _output(results)


@hygiene.command("completeness")
@click.pass_context
def hygiene_completeness(ctx):
    """Check edge schema completeness."""
    conn = get_connection()
    violations = check_completeness(conn)
    if not violations:
        click.echo("All nodes pass edge completeness checks.")
    elif ctx.obj.get("json_mode"):
        _output(violations)
    else:
        from .tui import format_hygiene
        format_hygiene("completeness", violations)


@hygiene.command("file-paths")
@click.pass_context
def hygiene_file_paths(ctx):
    """Validate file_path on structural nodes."""
    conn = get_connection()
    violations = check_file_paths(conn)
    if not violations:
        click.echo("All file_path checks pass.")
    elif ctx.obj.get("json_mode"):
        _output(violations)
    else:
        from .tui import format_hygiene
        format_hygiene("file-paths", violations)


@hygiene.command("content-drift")
@click.pass_context
def hygiene_content_drift(ctx):
    """Detect drift between brain content and context files."""
    conn = get_connection()
    issues = check_content_drift(conn)
    if not issues:
        click.echo("No content drift detected.")
    elif ctx.obj.get("json_mode"):
        _output(issues)
    else:
        from .tui import format_hygiene
        format_hygiene("content-drift", issues)


@hygiene.command("readiness")
@click.pass_context
def hygiene_readiness(ctx):
    """Check operational readiness."""
    conn = get_connection()
    violations = check_operational_readiness(conn)
    if ctx.obj.get("json_mode"):
        _output({"status": "clean" if not violations else "violations_found",
                 "count": len(violations), "violations": violations})
    elif not violations:
        click.echo("All operational readiness checks pass.")
    else:
        from .tui import format_hygiene
        format_hygiene("readiness", violations)


# --- Verify ---

@cli.command()
@click.argument("node_id", required=False)
@click.option("--stale", "stale_days", type=int, default=None, help="List nodes not verified in N days")
def verify(node_id, stale_days):
    """Mark a node as verified or find stale nodes.

    brain verify <id>          Set verified_at = now
    brain verify --stale 14    List stale nodes
    """
    conn = get_connection()

    if stale_days is not None:
        results = query_stale(conn, stale_days)
        if not results:
            click.echo(f"No nodes stale beyond {stale_days} days.")
        else:
            click.echo(f"{len(results)} nodes need verification:")
            _output(results)
        return

    if node_id is None:
        click.echo("Usage: brain verify <id> or brain verify --stale <days>", err=True)
        sys.exit(1)

    from .config import now
    from .writer import _ts_param
    ts = now()
    conn.execute(
        "MATCH (n:Node {id: $id}) SET n.verified_at = timestamp($ts)",
        parameters={"id": node_id, "ts": _ts_param(ts)},
    )
    click.echo(f"Verified: {node_id}")


# --- Config ---

@cli.group()
def config():
    """Manage brain configuration."""
    pass


@config.command("add-type")
@click.argument("type_name")
@click.argument("tier", type=click.Choice(["structural", "operational", "temporal"]))
def config_add_type(type_name, tier):
    """Register a custom type in a tier."""
    from .config import get_brain_dir
    config_path = get_brain_dir() / "config.json"
    if config_path.exists():
        cfg = json.loads(config_path.read_text())
    else:
        cfg = {"type_tiers": {}, "file_path_exceptions": []}

    tiers = cfg.setdefault("type_tiers", {})
    tier_types = tiers.setdefault(tier, [])
    if type_name not in tier_types:
        tier_types.append(type_name)
    config_path.write_text(json.dumps(cfg, indent=2))
    click.echo(f"Registered type '{type_name}' in tier '{tier}'")


@config.command("show")
def config_show():
    """Show current brain configuration."""
    from .config import get_brain_dir, get_type_tiers
    brain_dir = get_brain_dir()
    config_path = brain_dir / "config.json"
    click.echo(f"Brain directory: {brain_dir}")
    click.echo(f"Config file: {config_path}")
    if config_path.exists():
        click.echo(config_path.read_text())
    click.echo(f"\nEffective type tiers:")
    for tier, types in get_type_tiers().items():
        click.echo(f"  {tier}: {sorted(types)}")


# --- Dream ---

@cli.command()
@click.option("--dry-run", is_flag=True, help="Show what would be fixed without applying")
@click.pass_context
def dream(ctx, dry_run):
    """Run brain maintenance (hygiene, signals, optional conversation replay)."""
    from .tui import console as tui_console

    tui_console.print("[bold]Brain Dream[/] -- maintenance cycle\n")

    try:
        from memory.ingester import run_ingest
        run_ingest()
        tui_console.print("[green]v[/] Conversations indexed")
    except ImportError:
        tui_console.print("[dim]Skipping conversation ingest (memory not installed)[/]")
    except Exception as e:
        tui_console.print(f"[dim]Conversation ingest failed: {e}[/]")

    conn = get_connection()

    issues = []
    for name, check_fn in [
        ("duplicates", find_duplicates),
        ("orphans", find_orphans),
        ("completeness", check_completeness),
        ("file-paths", check_file_paths),
        ("verbs", audit_verbs),
        ("readiness", check_operational_readiness),
    ]:
        result = check_fn(conn)
        if result:
            issues.append((name, result))
            tui_console.print(f"[yellow]![/] {name}: {len(result)} issue(s)")
        else:
            tui_console.print(f"[green]v[/] {name}: clean")

    signal_results = compute_all_signals(conn)

    if ctx.obj.get("json_mode"):
        _output({"issues": [(n, r) for n, r in issues], "signals": signal_results})
    else:
        from .tui import format_signals
        format_signals(signal_results)

    if not dry_run:
        from .config import get_brain_dir
        import time
        last_dream_path = get_brain_dir() / ".last-dream"
        last_dream_path.write_text(str(int(time.time())))



# --- Viz ---

@cli.command()
@click.option("--port", default=8080, help="Port to serve on")
def viz(port):
    """Export fresh graph and serve visualization."""
    import functools
    import http.server
    import shutil
    import webbrowser

    conn = get_connection()
    path, nodes, edges = export_cytoscape(conn)
    click.echo(f"Exported {nodes} nodes, {edges} edges")

    from .config import get_brain_dir, get_viz_source_dir
    brain_dir = get_brain_dir()

    # Copy viz files to .brain/viz/ if not already there
    viz_dest = brain_dir / "viz"
    if not viz_dest.exists():
        viz_source = get_viz_source_dir()
        if viz_source.exists():
            shutil.copytree(viz_source, viz_dest)

    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(brain_dir)
    )
    server = http.server.HTTPServer(("localhost", port), handler)

    webbrowser.open(f"http://localhost:{port}/viz/")
    click.echo(f"Serving visualization at http://localhost:{port}/viz/")
    click.echo("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        click.echo("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    cli()
