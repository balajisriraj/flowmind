"""Shared helpers for the bundled MCP servers. Every path is confined to FLOWMIND_WORKSPACE."""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server.mcpserver.exceptions import ToolError


def root() -> Path:
    path = Path(os.environ.get("FLOWMIND_WORKSPACE", "workspace")).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def inside(relative: str) -> Path:
    """Resolve a workspace-relative path, refusing anything that escapes the workspace."""
    base = root()
    target = (base / relative.strip().lstrip("/")).resolve()
    if target != base and base not in target.parents:
        raise ToolError(f"'{relative}' is outside the workspace.")
    return target


def rel(path: Path) -> str:
    return path.relative_to(root()).as_posix()
