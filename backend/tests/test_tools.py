import json

import pytest
from conftest import open_hub

from flowmind.hub import ToolError


async def test_registry_comes_from_the_live_servers(settings):
    async with open_hub(settings) as hub:
        assert {"files.read_file", "sheets.append_row", "mail.draft_email", "notify.post_message"} <= set(hub.tools)
        assert hub.tools["files.read_file"].read_only and not hub.tools["files.move_file"].read_only
        assert "path: string" in hub.describe()


async def test_paths_are_confined_to_the_workspace(settings):
    async with open_hub(settings) as hub:
        with pytest.raises(ToolError, match="outside the workspace"):
            await hub.call("files.read_file", {"path": "../../../etc/hosts"})
        with pytest.raises(ToolError, match="outside the workspace"):
            await hub.call("files.write_file", {"path": "../evil.txt", "content": "x"})


async def test_tools_validate_their_inputs(settings):
    async with open_hub(settings) as hub:
        with pytest.raises(ToolError, match="Unknown columns"):
            await hub.call("sheets.append_row", {"path": "ledger.csv", "row": {"surprise": 1}})
        with pytest.raises(ToolError, match="not an email"):
            await hub.call("mail.draft_email", {"to": "nobody", "subject": "s", "body": "b"})
        out, _ = await hub.call("mail.draft_email", {"to": "a@b.example", "subject": "Hi", "body": "Body"})
        assert out["status"] == "drafted, not sent"
        assert json.loads((settings.workspace / out["path"]).read_text())["to"] == "a@b.example"
        rows, _ = await hub.call(
            "sheets.filter_rows", {"path": "tasks.csv", "column": "status", "op": "eq", "value": "overdue"}
        )
        assert rows["count"] == 2
