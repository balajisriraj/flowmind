"""MCP server: team notifications, appended to the workspace's notifications log (a stand-in for chat)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from ._workspace import inside

server = MCPServer("notify", instructions="Post short messages to team channels.")
LEVELS = {"info", "warning", "urgent"}


@server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False))
def post_message(channel: str, text: str, level: str = "info") -> dict:
    """Post a message to a team channel such as #finance. level is info, warning or urgent."""
    if level not in LEVELS:
        raise ToolError(f"level must be one of {sorted(LEVELS)}.")
    if not channel.startswith("#"):
        raise ToolError("channel must start with #, e.g. #finance.")
    entry = {
        "id": uuid.uuid4().hex[:10],
        "channel": channel,
        "text": text.strip(),
        "level": level,
        "at": datetime.now(UTC).isoformat(),
    }
    log = inside("notifications.jsonl")
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return {"id": entry["id"], "channel": channel}


if __name__ == "__main__":
    server.run()
