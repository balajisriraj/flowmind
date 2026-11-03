"""HTTP API. Builds and the activity feed stream as Server-Sent Events."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from .config import Settings, get_settings
from .service import Service

MAX_DROP = 2 * 1024 * 1024


class Describe(BaseModel):
    description: str = Field(min_length=10, max_length=4000)


class Note(BaseModel):
    note: str = Field(default="", max_length=2000)


def _sse(events):
    async def gen():
        async for event in events:
            yield {"event": event["type"], "data": json.dumps(event, default=str)}

    return EventSourceResponse(gen())


def create_app(settings: Settings | None = None, service: Service | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        svc = service or Service.from_settings(settings)
        await svc.start()
        app.state.service = svc
        try:
            yield
        finally:
            await svc.stop()

    app = FastAPI(title="FlowMind", version="0.1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])

    def svc(request: Request) -> Service:
        return request.app.state.service

    def wf_or_404(request: Request, wid: str) -> dict:
        wf = svc(request).store.get(wid)
        if not wf:
            raise HTTPException(404, "No such workflow.")
        return wf

    @app.get("/api/health")
    async def health(request: Request) -> dict:
        return {
            "status": "ok",
            "llm": settings.llm,
            "model": settings.model if settings.llm == "anthropic" else "scripted",
            "tools": len(svc(request).hub.tools),
        }

    @app.get("/api/registry")
    async def registry(request: Request) -> list[dict]:
        return svc(request).hub.registry()

    @app.get("/api/workflows")
    async def workflows(request: Request) -> list[dict]:
        s = svc(request)
        out = []
        for wf in s.store.workflows():
            runs = s.store.runs(wf["id"], 20)
            ok = sum(r["status"] == "succeeded" for r in runs)
            out.append(
                {k: wf[k] for k in ("id", "name", "description", "status", "created_at", "deployed_at", "last_run_at")}
                | {
                    "trigger": (wf["workflow"] or {}).get("trigger"),
                    "runs": len(runs),
                    "success_rate": ok / len(runs) if runs else None,
                }
            )
        return out

    @app.post("/api/workflows", status_code=201)
    async def create(body: Describe, request: Request) -> dict:
        return {"id": svc(request).create(body.description)}

    @app.get("/api/workflows/{wid}")
    async def get(wid: str, request: Request) -> dict:
        return wf_or_404(request, wid) | {"runs": svc(request).store.runs(wid, 30)}

    @app.delete("/api/workflows/{wid}")
    async def delete(wid: str, request: Request) -> dict:
        return {"deleted": svc(request).store.delete(wid)}

    @app.get("/api/workflows/{wid}/events")
    async def events(wid: str, request: Request) -> EventSourceResponse:
        wf_or_404(request, wid)
        return _sse(svc(request).events(wid))

    @app.post("/api/workflows/{wid}/rebuild")
    async def rebuild(wid: str, body: Note, request: Request) -> dict:
        wf_or_404(request, wid)
        svc(request).rebuild(wid, body.note)
        return {"ok": True}

    @app.post("/api/workflows/{wid}/deploy")
    async def deploy(wid: str, request: Request) -> dict:
        wf_or_404(request, wid)
        try:
            svc(request).deploy(wid)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"ok": True}

    @app.post("/api/workflows/{wid}/pause")
    async def pause(wid: str, request: Request) -> dict:
        wf_or_404(request, wid)
        svc(request).pause(wid)
        return {"ok": True}

    @app.post("/api/workflows/{wid}/run")
    async def run_now(wid: str, request: Request) -> dict:
        wf = wf_or_404(request, wid)
        if wf["status"] not in ("ready", "deployed", "paused"):
            raise HTTPException(409, "Build and dry-run the workflow first.")
        if wf["workflow"]["trigger"]["type"] == "file":
            raise HTTPException(409, "This workflow runs when a file arrives. Drop one in the inbox instead.")
        return await svc(request).run(wid, {"manual": True})

    @app.get("/api/alerts")
    async def alerts(request: Request) -> list[dict]:
        return svc(request).store.alerts()

    @app.post("/api/alerts/{aid}/ack")
    async def ack(aid: str, request: Request) -> dict:
        svc(request).store.acknowledge(aid)
        return {"ok": True}

    @app.get("/api/runs")
    async def runs(request: Request) -> list[dict]:
        return svc(request).store.runs(None, 50)

    @app.get("/api/activity")
    async def activity(request: Request) -> EventSourceResponse:
        return _sse(svc(request).activity.subscribe())

    @app.get("/api/workspace")
    async def workspace(request: Request) -> dict:
        return svc(request).workspace()

    @app.post("/api/workspace/inbox", status_code=201)
    async def drop(request: Request, file: UploadFile = File(...)) -> dict:
        data = await file.read(MAX_DROP + 1)
        if len(data) > MAX_DROP:
            raise HTTPException(413, "Files up to 2 MB, please.")
        return {"path": svc(request).drop(file.filename or "upload.txt", data)}

    @app.post("/api/workspace/samples/{name}", status_code=201)
    async def drop_sample(name: str, request: Request) -> dict:
        s = svc(request)
        sample = s.settings.fixtures / "samples" / name
        if sample.parent != s.settings.fixtures / "samples" or not sample.is_file():
            raise HTTPException(404, "No such sample.")
        return {"path": s.drop(name, sample.read_bytes())}

    return app
