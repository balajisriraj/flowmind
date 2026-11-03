"""MCP server: email drafts. Messages are written to the workspace outbox for review; nothing is ever sent."""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from ._workspace import inside, rel

server = MCPServer("mail", instructions="Draft emails into the outbox for a person to review and send.")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False))
def draft_email(to: str, subject: str, body: str) -> dict:
    """Draft an email to one recipient. It lands in the outbox for review; it is never sent automatically."""
    if not EMAIL.match(to.strip()):
        raise ToolError(f"'{to}' is not an email address.")
    if not subject.strip() or not body.strip():
        raise ToolError("subject and body are required.")
    message_id = uuid.uuid4().hex[:10]
    path = inside(f"outbox/{message_id}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "id": message_id,
                "to": to.strip(),
                "subject": subject.strip(),
                "body": body.strip(),
                "drafted_at": datetime.now(UTC).isoformat(),
            },
            indent=2,
        )
    )
    return {"id": message_id, "path": rel(path), "status": "drafted, not sent"}


if __name__ == "__main__":
    server.run()
