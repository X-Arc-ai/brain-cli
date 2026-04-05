"""Terminal UI formatting using Rich."""

from rich.console import Console
from rich.table import Table
from rich.tree import Tree
from rich.panel import Panel
from rich.text import Text
from rich import box

console = Console()

ACCENT = "#4ade80"
DIM = "#555555"

TYPE_COLORS = {
    "project": "#ba68c8",
    "person": "#fff176",
    "goal": "#aed581",
    "task": "#dce775",
    "decision": "#ffb74d",
    "blocker": "#e57373",
    "event": "#90a4ae",
    "observation": "#90a4ae",
    "status_change": "#90a4ae",
}

STATUS_COLORS = {
    "active": "green",
    "in_progress": "blue",
    "completed": "dim green",
    "blocked": "red",
    "stalled": "yellow",
    "pending": "cyan",
    "backlog": "dim",
    "archived": "dim",
    "cancelled": "dim red",
}


def format_scan(data: dict) -> None:
    """Format brain scan output as a Rich tree."""
    root_node = data["root"]
    tree = Tree(
        f"[bold]{root_node['title']}[/] "
        f"[dim]({root_node['type']})[/] "
        f"[{STATUS_COLORS.get(root_node.get('status', ''), 'white')}]"
        f"{root_node.get('status', '')}[/]"
    )

    for hop_num in sorted(data.get("nodes_by_hop", {}).keys()):
        nodes = data["nodes_by_hop"][hop_num]
        hop_branch = tree.add(f"[dim]hop {hop_num}[/] ({len(nodes)} nodes)")
        for node in nodes:
            color = TYPE_COLORS.get(node["type"], "white")
            status_color = STATUS_COLORS.get(node.get("status", ""), "white")
            hop_branch.add(
                f"[{color}]{node['id']}[/] "
                f"[dim]({node['type']})[/] "
                f"[{status_color}]{node.get('status', '')}[/]"
            )

    console.print(tree)
    console.print(f"\n[dim]{data['total_nodes']} nodes, "
                  f"{len(data.get('edges', []))} edges, "
                  f"depth {data['scan_depth']}[/]")


def format_signals(data: dict) -> None:
    """Format brain signals as a Rich table."""
    table = Table(title="Active Signals", box=box.ROUNDED)
    table.add_column("Type", style="bold")
    table.add_column("Node", style="cyan")
    table.add_column("Detail")
    table.add_column("Level", justify="center")

    level_colors = {"CRITICAL": "red", "WARNING": "yellow", "INFO": "blue"}

    for signal_type, items in data.get("signals", {}).items():
        for item in items:
            level = item.get("level", "INFO")
            color = level_colors.get(level, "white")
            detail = item.get("detail", item.get("message", item.get("days_stale", item.get("days_stuck", item.get("days_overdue", "")))))
            table.add_row(
                signal_type,
                item.get("id", item.get("node_id", item.get("source", ""))),
                str(detail),
                f"[{color}]{level}[/]",
            )

    if table.row_count == 0:
        console.print("[green]No active signals.[/]")
    else:
        console.print(table)

    summary = data.get("summary", {})
    if summary:
        parts = []
        for k, v in summary.items():
            if v > 0:
                parts.append(f"{k}: {v}")
        if parts:
            console.print(f"\n[dim]{', '.join(parts)}[/]")


def format_node(data: dict) -> None:
    """Format a single node as a Rich panel."""
    node_type = data.get("type", "unknown")
    color = TYPE_COLORS.get(node_type, "white")
    status = data.get("status", "")
    status_color = STATUS_COLORS.get(status, "white")

    header = Text()
    header.append(f"{data.get('title', data.get('id', ''))}", style="bold")
    header.append(f"  ({node_type})", style=f"{color}")
    header.append(f"  {status}", style=f"{status_color}")

    lines = []
    if data.get("content"):
        lines.append(data["content"][:500])
    if data.get("file_path"):
        lines.append(f"\n[dim]file: {data['file_path']}[/]")

    for edge in data.get("edges_out", []):
        lines.append(f"  -> [dim]{edge.get('verb', edge.get('e.verb', ''))}[/] -> {edge.get('target_id', edge.get('to', ''))}")
    for edge in data.get("edges_in", []):
        lines.append(f"  <- [dim]{edge.get('verb', edge.get('e.verb', ''))}[/] <- {edge.get('source_id', edge.get('from', ''))}")

    console.print(Panel("\n".join(lines), title=header, border_style=color))


def format_context(data: dict) -> None:
    """Format brain context output."""
    format_node(data)
    connected = data.get("connected", {})
    if connected:
        console.print(f"\n[dim]Connected ({data.get('connected_count', 0)} nodes):[/]")
        for type_name, nodes in connected.items():
            console.print(f"\n  [{TYPE_COLORS.get(type_name, 'white')}]{type_name}[/] ({len(nodes)})")
            for node in nodes:
                status_color = STATUS_COLORS.get(node.get("status", ""), "white")
                console.print(f"    {node['id']} [{status_color}]{node.get('status', '')}[/] -- {node.get('title', '')}")


def format_stats(data: dict) -> None:
    """Format brain stats as Rich panels."""
    type_table = Table(title="Nodes by Type", box=box.SIMPLE)
    type_table.add_column("Type", style="cyan")
    type_table.add_column("Count", justify="right")
    for item in data.get("nodes_by_type", []):
        type_name = item.get("type", "unknown")
        color = TYPE_COLORS.get(type_name, "white")
        type_table.add_row(f"[{color}]{type_name}[/]", str(item.get("count", 0)))

    console.print(type_table)
    console.print(f"\n[{ACCENT}]Total: {data.get('total_nodes', 0)} nodes, "
                  f"{data.get('total_edges', 0)} edges[/]")


def format_hygiene(check_name: str, results: list) -> None:
    """Format hygiene check results."""
    if not results:
        console.print(f"[green]v[/] {check_name}: no issues found")
        return

    console.print(f"[yellow]![/] {check_name}: {len(results)} issue(s)")
    for item in results[:20]:
        if isinstance(item, dict):
            msg = item.get("message", item.get("rule", item.get("issue", str(item))))
            node = item.get("node_id", item.get("id_a", ""))
            console.print(f"  [dim]-[/] {node}: {msg}")
        else:
            console.print(f"  [dim]-[/] {item}")


def format_search(results: list) -> None:
    """Format search results as a compact table."""
    table = Table(box=box.SIMPLE)
    table.add_column("ID", style="cyan")
    table.add_column("Type")
    table.add_column("Title")
    table.add_column("Status")
    table.add_column("Match", style="dim")

    for r in results:
        ntype = r.get("type", r.get("n.type", ""))
        color = TYPE_COLORS.get(ntype, "white")
        status = r.get("status", r.get("n.status", ""))
        status_color = STATUS_COLORS.get(status, "white")
        table.add_row(
            r.get("id", r.get("n.id", "")),
            f"[{color}]{ntype}[/]",
            r.get("title", r.get("n.title", "")),
            f"[{status_color}]{status}[/]",
            (r.get("match_snippet", "") or "")[:60],
        )

    console.print(table)
    console.print(f"\n[dim]{len(results)} result(s)[/]")
