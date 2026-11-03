import shutil
from contextlib import asynccontextmanager

import pytest

from flowmind.config import Settings
from flowmind.hub import ToolHub
from flowmind.llm import ScriptedLLM
from flowmind.service import Service
from flowmind.store import Store


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(llm="scripted", data_dir=tmp_path / "data", tick_seconds=3600)


# MCP stdio sessions must close in the task that opened them, so these are context managers used inside
# each test rather than async fixtures (pytest-asyncio may tear fixtures down in another task).
@asynccontextmanager
async def open_hub(settings: Settings):
    shutil.copytree(settings.fixtures / "workspace", settings.workspace)
    async with ToolHub(settings.workspace) as h:
        yield h


@asynccontextmanager
async def running(settings: Settings, llm=None):
    svc = Service(settings, llm or ScriptedLLM(), Store(settings.data_dir / "flowmind.db"))
    await svc.start()
    try:
        yield svc
    finally:
        await svc.stop()


INVOICE = "When a new invoice lands in the inbox, log it to the ledger, alert finance if it's over 5,000 and email the vendor."
