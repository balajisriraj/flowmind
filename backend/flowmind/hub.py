"""ToolHub: connects to MCP servers over stdio and exposes their tools as one registry.

The live hub stays connected for the life of the app. Dry runs open a separate hub whose servers point
at a throwaway copy of the workspace, so a dry run can never touch real files.
"""

from __future__ import annotations

import json
import os
import sys
import time
from contextlib import AsyncExitStack
from dataclasses import asdict, dataclass
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

BUNDLED = ["files", "sheets", "mail", "notify"]


@dataclass
class ToolInfo:
    server: str
    name: str
    description: str
    input_schema: dict
    read_only: bool

    @property
    def id(self) -> str:
        return f"{self.server}.{self.name}"

    def to_dict(self) -> dict:
        return {**asdict(self), "id": self.id}


class ToolError(RuntimeError):
    pass


class ToolHub:
    def __init__(self, workspace: Path, servers: list[str] | None = None) -> None:
        self.workspace = Path(workspace)
        self.servers = servers or BUNDLED
        self.sessions: dict[str, ClientSession] = {}
        self.tools: dict[str, ToolInfo] = {}
        self._stack: AsyncExitStack | None = None

    async def __aenter__(self) -> ToolHub:
        self._stack = AsyncExitStack()
        try:
            await self._connect()
        except BaseException:
            # Close whatever started, so a bad server fails loudly instead of leaving processes behind.
            await self._stack.aclose()
            raise
        return self

    async def _connect(self) -> None:
        assert self._stack is not None
        env = {**os.environ, "FLOWMIND_WORKSPACE": str(self.workspace)}
        for name in self.servers:
            params = StdioServerParameters(command=sys.executable, args=["-m", f"flowmind.servers.{name}"], env=env)
            read, write = await self._stack.enter_async_context(stdio_client(params))
            session = await self._stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            self.sessions[name] = session
            for tool in (await session.list_tools()).tools:
                hints = tool.annotations
                info = ToolInfo(
                    name, tool.name, tool.description or "", tool.input_schema, bool(hints and hints.read_only_hint)
                )
                self.tools[info.id] = info

    async def __aexit__(self, *exc) -> None:
        if self._stack:
            await self._stack.aclose()

    def registry(self) -> list[dict]:
        return [t.to_dict() for t in self.tools.values()]

    def describe(self) -> str:
        """The registry as the designer sees it: one block per tool with its argument schema."""
        blocks = []
        for t in self.tools.values():
            props = t.input_schema.get("properties", {})
            required = set(t.input_schema.get("required", []))
            args = ", ".join(f"{k}: {v.get('type', 'any')}{'' if k in required else '?'}" for k, v in props.items())
            blocks.append(f"- {t.id}({args}){' [read-only]' if t.read_only else ''}: {t.description}")
        return "\n".join(blocks)

    async def call(self, tool_id: str, args: dict) -> tuple[dict, float]:
        if tool_id not in self.tools:
            raise ToolError(f"Unknown tool {tool_id}.")
        server, name = tool_id.split(".", 1)
        started = time.perf_counter()
        result = await self.sessions[server].call_tool(name, args)
        ms = (time.perf_counter() - started) * 1000
        text = "".join(getattr(c, "text", "") for c in result.content)
        if result.is_error:
            raise ToolError(text.replace(f"Error executing tool {name}: ", ""))
        if result.structured_content is not None:
            return result.structured_content, ms
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = {"text": text}
        return data if isinstance(data, dict) else {"value": data}, ms
