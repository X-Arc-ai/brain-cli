"""Brain CLI -- Knowledge graph for structured memory in Claude Code."""

from importlib.metadata import version as _pkg_version, PackageNotFoundError

try:
    __version__ = _pkg_version("xarc-brain")
except PackageNotFoundError:  # editable install before metadata exists
    __version__ = "0.0.0+local"
