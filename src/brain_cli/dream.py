"""brain dream --phased -- Multi-session dream orchestrator.

Runs 6 maintenance phases as separate `claude -p` invocations with
temp-file state handoff. Each phase gets a fresh context window.

Targets Claude Code only. Non-Claude-Code runtimes should use the
single-session `brain dream` (without --phased).
"""

import json
import subprocess
import tempfile
from pathlib import Path

from .config import get_brain_dir, get_data_dir, get_runtime


def run_phased_dream(dry_run=False):
    """Run the 6-phase dream as separate agent sessions."""
    runtime = get_runtime()
    if runtime != "claude-code":
        raise RuntimeError(
            f"Phased dream requires claude-code runtime (current: {runtime}). "
            "Use 'brain dream' without --phased for single-session mode."
        )

    brain_dir = get_brain_dir()
    phases_dir = get_data_dir() / "skills" / "brain-dream" / "phases"
    preamble_path = phases_dir / "preamble.md"
    preamble = preamble_path.read_text() if preamble_path.exists() else ""

    protected = _load_protected_nodes(brain_dir)
    state = {"protected_nodes": protected, "phase_results": {}}

    for phase_num in range(1, 7):
        phase_file = phases_dir / f"phase{phase_num}.md"
        if not phase_file.exists():
            continue

        prompt = _build_phase_prompt(preamble, phase_file, state, phase_num)

        if dry_run:
            state["phase_results"][f"phase{phase_num}"] = {"status": "dry-run"}
            continue

        result = _run_agent_session(prompt)
        state["phase_results"][f"phase{phase_num}"] = result

        # Write interim state for crash recovery
        _write_state(brain_dir, state)

    # Write final report
    _write_report(brain_dir, state)
    return state


def _load_protected_nodes(brain_dir):
    """Read .brain/protected-nodes.json (empty array if missing)."""
    path = brain_dir / "protected-nodes.json"
    if path.exists():
        return json.loads(path.read_text())
    return []


def _build_phase_prompt(preamble, phase_file, state, phase_num):
    """Compose the full prompt: preamble + phase instructions + prior state."""
    phase_content = phase_file.read_text()
    state_json = json.dumps(state, indent=2, default=str)
    return (
        f"{preamble}\n\n---\n\n"
        f"{phase_content}\n\n---\n\n"
        f"## Prior Phase State\n\n```json\n{state_json}\n```"
    )


def _run_agent_session(prompt):
    """Run a single claude -p session and capture output."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(prompt)
        prompt_file = f.name

    try:
        result = subprocess.run(
            ["claude", "-p", "--output-format", "json", "-f", prompt_file],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode == 0:
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return {"status": "completed", "output": result.stdout[:2000]}
        else:
            return {"status": "error", "stderr": result.stderr[:1000]}
    except subprocess.TimeoutExpired:
        return {"status": "timeout"}
    except FileNotFoundError:
        return {"status": "error", "stderr": "claude CLI not found on PATH"}
    finally:
        Path(prompt_file).unlink(missing_ok=True)


def _write_state(brain_dir, state):
    """Write interim state for crash recovery."""
    path = brain_dir / ".dream-state.json"
    path.write_text(json.dumps(state, indent=2, default=str))


def _write_report(brain_dir, state):
    """Write the final dream report."""
    path = brain_dir / "last-dream-report.json"
    path.write_text(json.dumps(state, indent=2, default=str))
