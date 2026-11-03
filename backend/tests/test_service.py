from conftest import INVOICE, running

from flowmind.llm import ScriptedLLM
from flowmind.service import Service


async def build(service, description=INVOICE):
    wid = service.create(description)
    return wid, [e async for e in service.events(wid)]


async def test_build_fixes_the_design_and_dry_runs_in_a_sandbox(settings):
    async with running(settings) as service:
        ledger_before = (settings.workspace / "ledger.csv").read_text()
        wid, events = await build(service)
        stages = [e["stage"] for e in events if e["type"] == "stage"]
        assert stages == ["analyse", "design", "fix", "dry_run"]
        wf = service.store.get(wid)
        assert wf["status"] == "ready" and wf["fixes"] == 1
        assert all(s["status"] in ("ok", "skipped") for s in wf["dry_run"]["trace"])
        # The dry run wrote a ledger row and moved a file, but only in its sandbox.
        assert (settings.workspace / "ledger.csv").read_text() == ledger_before
        assert (settings.workspace / "inbox" / "harbourline-inv-4471.txt").exists()


async def test_deployed_file_trigger_handles_each_file_once(settings):
    async with running(settings) as service:
        wid, _ = await build(service)
        service.deploy(wid)
        assert await service.tick() == 1  # the invoice already in the inbox
        service.drop(
            "papercraft-inv-0093.txt", (settings.fixtures / "samples" / "papercraft-inv-0093.txt").read_bytes()
        )
        assert await service.tick() == 1
        assert await service.tick() == 0
        runs = service.store.runs(wid)
        assert [r["status"] for r in runs] == ["succeeded", "succeeded"]
        small = next(r for r in runs if r["trigger"]["name"].startswith("papercraft"))
        assert next(s for s in small["trace"] if s["id"] == "alert")["status"] == "skipped"
        ws = service.workspace()
        assert ws["inbox"] == [] and len(ws["outbox"]) == 2 and len(ws["ledger"]) == 3


async def test_failing_runs_raise_alerts(settings):
    async with running(settings) as service:
        wid, _ = await build(service)
        service.deploy(wid)
        (settings.workspace / "ledger.csv").write_text("only,these,columns\n")  # the ledger changed shape under us
        await service.tick()
        run = service.store.runs(wid)[0]
        assert run["status"] == "failed" and "log" in run["error"]
        assert service.store.alerts()[0]["level"] == "error"


async def test_design_that_never_validates_stops(settings):
    class Stubborn(ScriptedLLM):
        def _design(self, prompt):
            wf = super()._design(prompt.replace("<problems>", "<p>"))
            wf["steps"][0]["tool"] = "files.does_not_exist"
            return wf

    from flowmind.store import Store

    svc = Service(settings.model_copy(update={"max_fixes": 2}), Stubborn(), Store(settings.data_dir / "x.db"))
    await svc.start()
    try:
        wid, events = await build(svc)
        assert [e["type"] for e in events].count("validation") == 3
        assert svc.store.get(wid)["status"] == "needs_work"
        try:
            svc.deploy(wid)
            raise AssertionError("deploy should refuse")
        except ValueError:
            pass
    finally:
        await svc.stop()
