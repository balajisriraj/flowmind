"""The FlowMind runtime: builds workflows, runs deployed ones on their triggers, and monitors every run."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import shutil
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

from . import monitor
from .builder import Builder
from .config import Settings
from .engine import execute
from .hub import ToolHub
from .llm import LLM, LLMRefusal, make_llm
from .spec import Workflow
from .store import Store

log = logging.getLogger("flowmind")


class Bus:
    """Replayable event stream: late subscribers get the history first, then live events."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self.closed = False
        self._changed = asyncio.Condition()

    async def publish(self, event: dict, final: bool = False) -> None:
        async with self._changed:
            self.events.append(event)
            self.closed = self.closed or final
            self._changed.notify_all()

    async def subscribe(self) -> AsyncIterator[dict]:
        seen = 0
        while True:
            async with self._changed:
                await self._changed.wait_for(lambda seen=seen: len(self.events) > seen or self.closed)
                fresh, seen, closed = self.events[seen:], len(self.events), self.closed
            for event in fresh:
                yield event
            if closed and seen == len(self.events):
                return


class Broadcast:
    """Live-only fan-out: each subscriber gets events from the moment it subscribes."""

    def __init__(self) -> None:
        self.queues: set[asyncio.Queue] = set()

    async def publish(self, event: dict) -> None:
        for q in self.queues:
            q.put_nowait(event)

    async def subscribe(self) -> AsyncIterator[dict]:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self.queues.add(q)
        try:
            while True:
                yield await q.get()
        finally:
            self.queues.discard(q)


@dataclass
class Service:
    settings: Settings
    llm: LLM
    store: Store
    hub: ToolHub | None = None
    buses: dict[str, Bus] = field(default_factory=dict)
    activity: Broadcast = field(default_factory=Broadcast)  # live feed of runs for the monitor page
    _tasks: set[asyncio.Task] = field(default_factory=set)
    _running: set[str] = field(default_factory=set)

    @classmethod
    def from_settings(cls, settings: Settings, llm: LLM | None = None) -> Service:
        return cls(settings, llm or make_llm(settings), Store(settings.data_dir / "flowmind.db"))

    # ── lifecycle (enter and exit in the same task: MCP stdio sessions require it) ──
    async def start(self) -> None:
        ws = self.settings.workspace
        if not ws.exists():
            shutil.copytree(self.settings.fixtures / "workspace", ws)
        self.hub = await ToolHub(ws).__aenter__()
        self._spawn(self._runner())

    async def stop(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        for task in list(self._tasks):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        if self.hub:
            await self.hub.__aexit__(None, None, None)

    def _spawn(self, coro) -> asyncio.Task:
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    # ── build ──
    def create(self, description: str) -> str:
        wid = self.store.create(description.strip())
        self.buses[wid] = Bus()
        self._spawn(self._build(wid))
        return wid

    def rebuild(self, wid: str, note: str = "") -> None:
        wf = self.store.get(wid)
        description = wf["description"] + (f"\n\nAlso: {note.strip()}" if note.strip() else "")
        self.store.update(wid, description=description, status="building", error=None)
        self.buses[wid] = Bus()
        self._spawn(self._build(wid))

    async def _build(self, wid: str) -> None:
        bus = self.buses[wid]
        assert self.hub is not None
        builder = Builder(self.llm, self.settings, self.hub.describe(), self.hub.tools).build()
        final: dict = {}
        rounds: list[list[str]] = []  # every validation result, so the fix history survives a reload
        try:
            description = self.store.get(wid)["description"]
            async for mode, chunk in builder.astream({"description": description}, stream_mode=["custom", "values"]):
                if mode == "custom":
                    if chunk["type"] == "analysis":
                        self.store.update(wid, analysis=chunk["analysis"])
                    elif chunk["type"] == "workflow":
                        self.store.update(wid, workflow=chunk["workflow"], name=chunk["workflow"]["name"])
                    elif chunk["type"] == "validation":
                        rounds.append(chunk["problems"])
                        self.store.update(wid, validation=rounds)
                    elif chunk["type"] == "dry_run":
                        self.store.update(wid, dry_run=chunk["result"])
                    await bus.publish(chunk)
                else:
                    final = chunk
            status = final.get("status") or ("needs_work" if final.get("problems") else "ready")
            self.store.update(wid, status=status, fixes=final.get("fixes", 0))
            await bus.publish({"type": "done", "status": status, "fixes": final.get("fixes", 0)}, final=True)
        except Exception as exc:
            log.exception("build failed for %s", wid)
            message = (
                "Claude declined to design this automation."
                if isinstance(exc, LLMRefusal)
                else "The build failed. Try again?"
            )
            self.store.update(wid, status="failed", error=message)
            await bus.publish({"type": "error", "message": message}, final=True)

    async def events(self, wid: str) -> AsyncIterator[dict]:
        bus = self.buses.get(wid)
        if bus is None:
            wf = self.store.get(wid)
            yield {"type": "done", "status": wf["status"], "fixes": wf["fixes"]}
            return
        async for event in bus.subscribe():
            yield event

    # ── deploy and run ──
    def deploy(self, wid: str) -> None:
        from .store import now

        wf = self.store.get(wid)
        if wf["status"] not in ("ready", "paused"):
            raise ValueError("Only a workflow that passed its dry run can be deployed.")
        self.store.update(wid, status="deployed", deployed_at=now())

    def pause(self, wid: str) -> None:
        self.store.update(wid, status="paused")

    async def run(self, wid: str, trigger: dict) -> dict:
        assert self.hub is not None
        wf_row = self.store.get(wid)
        wf = Workflow.model_validate(wf_row["workflow"])
        history = self.store.runs(wid, 20)
        result = await execute(wf, self.hub, self.llm, trigger)
        run_id = self.store.add_run(wid, trigger, result)
        for level, message in monitor.check(result, history, wf_row["dry_run"]):
            self.store.alert(wid, run_id, level, message)
        event = {
            "type": "run",
            "workflow_id": wid,
            "name": wf.name,
            "run_id": run_id,
            "status": result["status"],
            "ms": result["ms"],
        }
        await self.activity.publish(event)
        return {"id": run_id, **result}

    async def tick(self) -> int:
        """One pass of the runner: fire due schedules and new files. Returns how many runs started."""
        from datetime import UTC, datetime

        started = 0
        for row in self.store.workflows():
            if row["status"] != "deployed" or row["id"] in self._running:
                continue
            trigger = row["workflow"]["trigger"]
            fires: list[dict] = []
            if trigger["type"] == "schedule":
                # A schedule runs once on deploy, then every N minutes.
                last = row["last_run_at"]
                elapsed = (datetime.now(UTC) - datetime.fromisoformat(last)).total_seconds() if last else 1e9
                if elapsed >= trigger["every_minutes"] * 60:
                    fires.append({})
            elif trigger["type"] == "file":
                folder = self.settings.workspace / trigger["folder"]
                for path in sorted(folder.glob(trigger["pattern"] or "*")) if folder.is_dir() else []:
                    rel = path.relative_to(self.settings.workspace).as_posix()
                    if path.is_file() and self.store.claim(row["id"], f"{rel}:{path.stat().st_mtime_ns}"):
                        fires.append({"file": rel, "name": path.name})
            for t in fires:
                self._running.add(row["id"])
                try:
                    await self.run(row["id"], t)
                    started += 1
                finally:
                    self._running.discard(row["id"])
        return started

    async def _runner(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception("runner tick failed")
            await asyncio.sleep(self.settings.tick_seconds)

    # ── workspace view ──
    def workspace(self) -> dict:
        ws = self.settings.workspace

        def files(folder: str) -> list[str]:
            d = ws / folder
            return sorted(p.name for p in d.iterdir() if p.is_file()) if d.is_dir() else []

        def table(name: str) -> list[dict]:
            import csv

            p = ws / name
            if not p.exists():
                return []
            with p.open(newline="", encoding="utf-8") as f:
                return list(csv.DictReader(f))

        outbox = (
            sorted((ws / "outbox").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:10]
            if (ws / "outbox").is_dir()
            else []
        )
        notes = (
            (ws / "notifications.jsonl").read_text(encoding="utf-8").splitlines()[-20:]
            if (ws / "notifications.jsonl").exists()
            else []
        )
        samples = sorted(p.name for p in (self.settings.fixtures / "samples").glob("*"))
        return {
            "inbox": files("inbox"),
            "processed": files("processed"),
            "ledger": table("ledger.csv"),
            "tasks": table("tasks.csv"),
            "outbox": [json.loads(p.read_text()) for p in outbox],
            "notifications": [json.loads(n) for n in reversed(notes)],
            "samples": samples,
        }

    def drop(self, name: str, data: bytes) -> str:
        """Put a file in the inbox, as if it had just arrived."""
        target = self.settings.workspace / "inbox" / Path(name).name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return f"inbox/{target.name}"
