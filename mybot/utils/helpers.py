"""Utility functions for mybot."""

import os
import re
from datetime import datetime
from pathlib import Path

# Process-level data directory. Set by the CLI based on --workspace / env / default.
_ACTIVE_DATA_DIR: Path | None = None

DEFAULT_DATA_DIR = Path.home() / ".mybot"


def ensure_dir(path: Path) -> Path:
    """Ensure directory exists, return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_data_dir(workspace: str | None) -> Path:
    """Resolve a workspace argument to a data directory.

    `workspace` may be:
      - None → use env `MYBOT_WORKSPACE` if set, otherwise `~/.mybot`.
      - A path-like value (contains `/`, `\\`, starts with `~` or `.`) → treated
        as an explicit data dir.
      - Any other string → a named workspace under `~/.mybot/workspaces/<name>`.
    """
    arg = workspace if workspace is not None else os.environ.get("MYBOT_WORKSPACE")
    if not arg:
        return DEFAULT_DATA_DIR
    if any(c in arg for c in ("/", "\\")) or arg.startswith(("~", ".")):
        return Path(arg).expanduser().resolve()
    return DEFAULT_DATA_DIR / "workspaces" / arg


def set_active_data_dir(path: Path) -> Path:
    """Set the process-wide active data directory and return it."""
    global _ACTIVE_DATA_DIR
    _ACTIVE_DATA_DIR = path
    return path


def get_data_path() -> Path:
    """Active mybot data directory (set by CLI; defaults to ~/.mybot)."""
    return ensure_dir(_ACTIVE_DATA_DIR or DEFAULT_DATA_DIR)


def get_workspace_path(workspace: str | None = None) -> Path:
    """Resolve and ensure the agent workspace path.

    Defaults to `<data_dir>/workspace`. An explicit path overrides.
    """
    if workspace:
        return ensure_dir(Path(workspace).expanduser())
    return ensure_dir(get_data_path() / "workspace")


def list_named_workspaces() -> list[str]:
    """List named workspaces under ~/.mybot/workspaces/."""
    root = DEFAULT_DATA_DIR / "workspaces"
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def timestamp() -> str:
    """Current ISO timestamp."""
    return datetime.now().isoformat()


_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*]')

def safe_filename(name: str) -> str:
    """Replace unsafe path characters with underscores."""
    return _UNSAFE_CHARS.sub("_", name).strip()


def sync_workspace_templates(workspace: Path, silent: bool = False) -> list[str]:
    """Sync bundled templates to workspace. Only creates missing files."""
    from importlib.resources import files as pkg_files
    try:
        tpl = pkg_files("mybot") / "templates"
    except Exception:
        return []
    if not tpl.is_dir():
        return []

    added: list[str] = []

    def _write(src, dest: Path):
        if dest.exists():
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(src.read_text(encoding="utf-8") if src else "", encoding="utf-8")
        added.append(str(dest.relative_to(workspace)))

    for item in tpl.iterdir():
        if item.name.endswith(".md"):
            _write(item, workspace / item.name)
    _write(tpl / "memory" / "MEMORY.md", workspace / "memory" / "MEMORY.md")
    _write(None, workspace / "memory" / "HISTORY.md")
    (workspace / "skills").mkdir(exist_ok=True)

    if added and not silent:
        from rich.console import Console
        for name in added:
            Console().print(f"  [dim]Created {name}[/dim]")
    return added
