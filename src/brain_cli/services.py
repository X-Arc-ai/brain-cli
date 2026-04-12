"""brain service -- Background service packaging for viz and dream.

Generates and installs launchd (macOS) or systemd (Linux) service files
from bundled templates, substituting the user's brain path and binary location.
"""

import platform
import shutil
import subprocess
from pathlib import Path
from string import Template

from .config import get_brain_dir, get_data_dir


def install_service(service_name):
    """Install a launchd/systemd service for viz or dream."""
    if service_name not in ("viz", "dream"):
        raise ValueError(f"Unknown service: {service_name}. Must be 'viz' or 'dream'.")

    brain_path = shutil.which("brain")
    if not brain_path:
        raise RuntimeError("'brain' not found on PATH")

    is_macos = platform.system() == "Darwin"
    template_file, dest_dir = _resolve_paths(service_name, is_macos)

    template_path = get_data_dir() / "services" / template_file
    if not template_path.exists():
        raise FileNotFoundError(f"Service template not found: {template_path}")

    template_content = template_path.read_text()
    rendered = Template(template_content).substitute(
        BRAIN_PATH=brain_path,
        BRAIN_DIR=str(get_brain_dir()),
        HOME=str(Path.home()),
    )

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / template_file
    dest_path.write_text(rendered)

    _load_service(dest_path, is_macos)
    return str(dest_path)


def uninstall_service(service_name):
    """Uninstall a previously installed service."""
    if service_name not in ("viz", "dream"):
        raise ValueError(f"Unknown service: {service_name}. Must be 'viz' or 'dream'.")

    is_macos = platform.system() == "Darwin"
    template_file, dest_dir = _resolve_paths(service_name, is_macos)
    dest_path = dest_dir / template_file

    if not dest_path.exists():
        raise FileNotFoundError(f"Service file not found: {dest_path}")

    _unload_service(dest_path, is_macos)
    dest_path.unlink()
    return str(dest_path)


def _resolve_paths(service_name, is_macos):
    if is_macos:
        template_file = f"ai.x-arc.brain-{service_name}.plist"
        dest_dir = Path.home() / "Library" / "LaunchAgents"
    else:
        template_file = f"brain-{service_name}.service"
        dest_dir = Path.home() / ".config" / "systemd" / "user"
    return template_file, dest_dir


def _load_service(path, is_macos):
    if is_macos:
        subprocess.run(["launchctl", "load", str(path)], check=True)
    else:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", "--now", path.stem], check=True)


def _unload_service(path, is_macos):
    if is_macos:
        subprocess.run(["launchctl", "unload", str(path)], check=True)
    else:
        subprocess.run(["systemctl", "--user", "disable", "--now", path.stem], check=True)
