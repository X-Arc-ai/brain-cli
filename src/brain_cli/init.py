"""brain init -- Zero-to-graph onboarding."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.tree import Tree
from rich.panel import Panel
from rich.prompt import Confirm

from .config import get_brain_dir, get_project_root, get_data_dir, set_brain_dir
from .database import get_connection
from .writer import execute_batch

console = Console()

_PROJECT_MANIFESTS = [
    ("package.json", "name"),
    ("pyproject.toml", None),
    ("setup.py", None),
    ("Cargo.toml", None),
    ("go.mod", None),
    ("pom.xml", None),
    ("build.gradle", None),
    ("Gemfile", None),
    ("composer.json", "name"),
    ("CMakeLists.txt", None),
    ("Makefile", None),
]


def run_init(project_root=None, skip_memory=False, skip_hooks=False, skip_viz=False, yes=False):
    """Run the full brain init flow."""
    root = Path(project_root) if project_root else Path.cwd()

    # CRITICAL: Create .brain/ in project root and override config BEFORE
    # any database operations. Without this, config resolves to ~/.brain/
    brain_dir = root / ".brain"
    set_brain_dir(brain_dir)
    if project_root:
        os.environ["BRAIN_PROJECT_ROOT"] = str(root)

    console.print(Panel(
        "[bold]brain init[/]\n\n"
        "Analyzing your project to bootstrap a knowledge graph.",
        border_style="#4ade80",
    ))

    _step_1_create_dirs(brain_dir)

    if not skip_memory:
        _step_2_index_conversations()

    proposals = _step_3_analyze_project(root)

    if proposals:
        _step_4_show_proposals(proposals, skip_viz, yes=yes)

    if not skip_hooks:
        _step_5_install_behaviors(root, brain_dir, yes=yes)

    console.print(f"\n[#4ade80]Brain initialized.[/] "
                  f"Your graph is at [dim]{brain_dir}[/]")


def _step_1_create_dirs(brain_dir):
    """Create brain directory structure."""
    brain_dir.mkdir(parents=True, exist_ok=True)
    (brain_dir / "db").mkdir(exist_ok=True)
    (brain_dir / "exports").mkdir(exist_ok=True)

    viz_dest = brain_dir / "viz"
    if not viz_dest.exists():
        viz_source = get_data_dir() / "viz"
        if viz_source.exists():
            shutil.copytree(viz_source, viz_dest)

    config_path = brain_dir / "config.json"
    if not config_path.exists():
        brain_path = shutil.which("brain") or ""
        config_path.write_text(json.dumps({
            "type_tiers": {},
            "file_path_exceptions": [],
            "brain_path": brain_path,
        }, indent=2))

    # Eagerly initialize the DB so the schema is in place after init returns.
    get_connection()

    console.print("[green]v[/] Brain directory created")


def _step_2_index_conversations():
    """Index conversation history via agent-memory."""
    try:
        from memory.ingester import run_ingest
        console.print("[dim]Indexing conversation history...[/]")
        run_ingest()
        console.print("[green]v[/] Conversation history indexed")
    except ImportError:
        console.print("[dim]Skipping conversation history "
                      "(install with: pip install agent-memory from git+https://github.com/X-Arc-ai/memory.git)[/]")
    except Exception as e:
        console.print(f"[dim]Conversation indexing failed: {e}[/]")


def _step_3_analyze_project(root):
    """Analyze project structure and propose graph nodes."""
    proposals = []
    project_node_id = None

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Scanning project...", total=None)

        for manifest_file, name_key in _PROJECT_MANIFESTS:
            manifest_path = root / manifest_file
            if not manifest_path.exists():
                continue

            title = root.name
            if name_key and manifest_file.endswith(".json"):
                try:
                    pkg = json.loads(manifest_path.read_text())
                    title = pkg.get(name_key, root.name)
                except (json.JSONDecodeError, KeyError):
                    pass

            project_node_id = _slugify(title)
            proposals.append({
                "op": "create_node",
                "id": project_node_id,
                "type": "project",
                "title": title,
                "status": "active",
                "content": f"Project detected from {manifest_file}",
                "file_path": manifest_file,
            })
            break

        if not project_node_id and (root / "README.md").exists():
            project_node_id = _slugify(root.name)
            proposals.append({
                "op": "create_node",
                "id": project_node_id,
                "type": "project",
                "title": root.name,
                "status": "active",
                "file_path": "README.md",
            })

        if project_node_id:
            try:
                result = subprocess.run(
                    ["git", "log", "--format=%aN", "--since=90 days ago"],
                    capture_output=True, text=True, cwd=str(root), timeout=10,
                )
                if result.returncode == 0:
                    authors = set(result.stdout.strip().split("\n"))
                    authors.discard("")
                    for author in list(authors)[:10]:
                        slug = _slugify(author)
                        if slug == project_node_id:
                            slug = f"person-{slug}"
                        proposals.append({
                            "op": "create_node",
                            "id": slug,
                            "type": "person",
                            "title": author,
                            "status": "active",
                            "content": f"Contributor to {root.name}",
                        })
                        proposals.append({
                            "op": "create_edge",
                            "from": slug,
                            "to": project_node_id,
                            "verb": "contributes to",
                        })
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        progress.update(task, description="Scan complete")

    return proposals


def _step_4_show_proposals(proposals, skip_viz, yes=False):
    """Show proposed graph and ask for confirmation."""
    nodes = [p for p in proposals if p.get("op") == "create_node"]
    edges = [p for p in proposals if p.get("op") == "create_edge"]

    tree = Tree("[bold]Proposed Graph[/]")
    for node in nodes:
        tree.add(f"{node['id']} [dim]({node['type']})[/] -- {node.get('title', '')}")

    console.print(tree)
    console.print(f"\n[dim]{len(nodes)} nodes, {len(edges)} edges[/]")

    if yes or Confirm.ask("\nApply this graph?", default=True):
        conn = get_connection()
        result = execute_batch(conn, proposals)
        summary = result[-1]["summary"]
        console.print(f"[green]v[/] Graph created: "
                      f"{summary['total']} operations "
                      f"({summary['created_nodes']} nodes, "
                      f"{summary['created_edges']} edges)")

        if not skip_viz:
            from .exporter import export_cytoscape
            export_cytoscape(get_connection())
            console.print("\nOpening visualization...")
            _open_viz()
    else:
        console.print("[dim]Skipped. You can run brain init again anytime.[/]")


def _step_5_install_behaviors(root, brain_dir, yes=False):
    """Install CLAUDE.md, hooks, and brain-dream skill."""
    claude_dir = root / ".claude"

    if not claude_dir.exists():
        if not yes and not Confirm.ask(
            "Install Claude Code integration (CLAUDE.md + hooks)?",
            default=True,
        ):
            return

    brain_claude_md = _get_brain_claude_md()
    claude_md_path = root / "CLAUDE.md"

    if claude_md_path.exists():
        existing = claude_md_path.read_text()
        if "## Brain" not in existing and "brain scan" not in existing:
            with open(claude_md_path, "a") as f:
                f.write("\n\n" + brain_claude_md)
            console.print("[green]v[/] Brain instructions appended to CLAUDE.md")
        else:
            console.print("[dim]CLAUDE.md already has brain instructions[/]")
    else:
        claude_md_path.write_text(brain_claude_md)
        console.print("[green]v[/] CLAUDE.md created with brain instructions")

    _install_hooks(root, brain_dir)
    _install_dream_skill()

    console.print("[green]v[/] Hooks and skill installed")


def _install_hooks(root, brain_dir):
    """Copy hooks to .brain/hooks/ and register in settings.local.json."""
    data_dir = get_data_dir()
    hooks_source = data_dir / "hooks"
    if not hooks_source.exists():
        console.print("[dim]Hook files not found, skipping[/]")
        return

    hooks_dest = brain_dir / "hooks"
    if hooks_dest.exists():
        shutil.rmtree(hooks_dest)
    shutil.copytree(hooks_source, hooks_dest)

    for sh_file in hooks_dest.glob("*.sh"):
        sh_file.chmod(0o755)

    settings_path = root / ".claude" / "settings.local.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    if settings_path.exists():
        settings = json.loads(settings_path.read_text())
    else:
        settings = {}

    hooks = settings.setdefault("hooks", {})

    user_hooks = hooks.setdefault("UserPromptSubmit", [])
    if not any("brain-reminder" in str(h) for h in user_hooks):
        user_hooks.append({
            "type": "command",
            "command": f"bash {hooks_dest / 'brain-reminder.sh'}",
            "timeout": 5000,
        })

    pre_hooks = hooks.setdefault("PreToolUse", [])
    if not any("validate-brain-write" in str(h) for h in pre_hooks):
        pre_hooks.append({
            "type": "command",
            "command": f"bash {hooks_dest / 'validate-brain-write.sh'}",
            "timeout": 15000,
            "matcher": "Bash",
        })

    stop_hooks = hooks.setdefault("Stop", [])
    if not any("verify-cognitive-loop" in str(h) for h in stop_hooks):
        stop_hooks.append({
            "type": "command",
            "command": f"bash {hooks_dest / 'verify-cognitive-loop.sh'}",
            "timeout": 10000,
        })

    if not any("dream-hook" in str(h) for h in stop_hooks):
        stop_hooks.append({
            "type": "command",
            "command": f"bash {hooks_dest / 'dream-hook.sh'}",
            "timeout": 5000,
        })

    settings_path.write_text(json.dumps(settings, indent=2))


def _install_dream_skill():
    """Install brain-dream skill to ~/.claude/skills/."""
    data_dir = get_data_dir()
    skill_source = data_dir / "skills" / "brain-dream" / "SKILL.md"
    if not skill_source.exists():
        return

    skill_dest = Path.home() / ".claude" / "skills" / "brain-dream"
    skill_dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(skill_source, skill_dest / "SKILL.md")


def _get_brain_claude_md():
    """Return the CLAUDE.md content for brain integration."""
    claude_md_path = get_data_dir() / "CLAUDE.md"
    if claude_md_path.exists():
        return claude_md_path.read_text()
    return _FALLBACK_CLAUDE_MD


_FALLBACK_CLAUDE_MD = """## Brain (Knowledge Graph)

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

### Commands
- `brain scan <id>` -- topology map (start here)
- `brain context <id>` -- deep dive
- `brain search "<term>"` -- find nodes
- `brain signals` -- what needs attention
- `brain write node --json-data '{...}'` -- create/update node
- `brain write edge --json-data '{...}'` -- create/update edge
"""


def _open_viz():
    """Open the brain visualization."""
    brain_dir = get_brain_dir()
    config_path = brain_dir / "config.json"
    brain_cmd = "brain"
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text())
            brain_cmd = cfg.get("brain_path", "brain") or "brain"
        except (json.JSONDecodeError, KeyError):
            pass
    subprocess.Popen(
        [brain_cmd, "viz"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _slugify(text):
    """Convert text to a node ID slug."""
    slug = text.lower().strip()
    slug = re.sub(r'[^a-z0-9\s_-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')[:50]
