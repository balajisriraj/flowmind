import json

from fastapi.testclient import TestClient

from flowmind.api import create_app
from flowmind.llm import ScriptedLLM
from flowmind.service import Service
from flowmind.store import Store


def sse(text: str) -> list[dict]:
    return [json.loads(line[5:]) for line in text.splitlines() if line.startswith("data:")]


def test_end_to_end_over_http(settings):
    svc = Service(settings, ScriptedLLM(), Store(settings.data_dir / "flowmind.db"))
    with TestClient(create_app(settings, svc)) as c:
        assert c.get("/api/health").json()["tools"] == 9
        assert len(c.get("/api/registry").json()) == 9
        assert c.post("/api/workflows", json={"description": "short"}).status_code == 422
        wid = c.post(
            "/api/workflows",
            json={"description": "Every minute, post overdue tasks from the tracker to the team channel."},
        ).json()["id"]
        assert sse(c.get(f"/api/workflows/{wid}/events").text)[-1] == {"type": "done", "status": "ready", "fixes": 1}
        run = c.post(f"/api/workflows/{wid}/run").json()
        assert run["status"] == "succeeded"
        assert c.post(f"/api/workflows/{wid}/deploy").json() == {"ok": True}
        listing = c.get("/api/workflows").json()[0]
        assert listing["status"] == "deployed" and listing["success_rate"] == 1.0
        assert c.post("/api/workspace/samples/../../etc/passwd").status_code == 404
        assert c.post("/api/workspace/samples/papercraft-inv-0093.txt").json() == {
            "path": "inbox/papercraft-inv-0093.txt"
        }
        assert "papercraft-inv-0093.txt" in c.get("/api/workspace").json()["inbox"]
