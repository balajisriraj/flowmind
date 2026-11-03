"""MCP server: files in the workspace (an inbox, processed folders, documents)."""

from __future__ import annotations

import shutil

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from ._workspace import inside, rel

server = MCPServer("files", instructions="Read, list and move files inside the FlowMind workspace.")
READ = ToolAnnotations(read_only_hint=True)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True)


@server.tool(annotations=READ)
def list_files(folder: str, pattern: str = "*") -> dict:
    """List files in a workspace folder, optionally filtered by a glob pattern such as *.txt."""
    path = inside(folder)
    if not path.is_dir():
        raise ToolError(f"No folder '{folder}'.")
    files = sorted(rel(p) for p in path.glob(pattern) if p.is_file())
    return {"files": files, "count": len(files)}


@server.tool(annotations=READ)
def read_file(path: str) -> dict:
    """Read a text file from the workspace."""
    target = inside(path)
    if not target.is_file():
        raise ToolError(f"No file '{path}'.")
    text = target.read_text(encoding="utf-8", errors="replace")
    return {"path": rel(target), "name": target.name, "content": text[:20000], "size": target.stat().st_size}


@server.tool(annotations=WRITE)
def move_file(path: str, folder: str) -> dict:
    """Move a workspace file into another workspace folder (created if needed). Returns the new path."""
    source = inside(path)
    if not source.is_file():
        raise ToolError(f"No file '{path}'.")
    dest_dir = inside(folder)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / source.name
    shutil.move(source, dest)
    return {"path": rel(dest)}


@server.tool(annotations=WRITE)
def write_file(path: str, content: str) -> dict:
    """Write a text file in the workspace, replacing it if it exists."""
    target = inside(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"path": rel(target), "size": len(content)}


if __name__ == "__main__":
    server.run()
