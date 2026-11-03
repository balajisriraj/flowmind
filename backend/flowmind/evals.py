"""End-to-end evaluation: describe each example process, build it, deploy it, and trigger it for real."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from .config import get_settings
from .service import Service

EXAMPLES = [
    (
        "Invoice intake",
        "When a new invoice lands in the inbox, log it to the ledger, alert finance if it's over 5,000, email the vendor to confirm we got it, and file it away.",
    ),
    ("Overdue digest", "Every minute, check the task tracker for overdue tasks and post a digest to the team channel."),
]


async def run(verbose: bool = False) -> bool:
    settings = get_settings().model_copy(update={"data_dir": Path(tempfile.mkdtemp(prefix="flowmind-eval-"))})
    service = Service.from_settings(settings)
    await service.start()
    ok = True
    try:
        for title, description in EXAMPLES:
            wid = service.create(description)
            events = [e async for e in service.events(wid)]
            wf = service.store.get(wid)
            problems = [e["problems"] for e in events if e["type"] == "validation"]
            dry = wf["dry_run"] or {}
            built = wf["status"] == "ready"
            print(
                f"{'PASS' if built else 'FAIL'}  {title}: {wf['status']} after {wf['fixes']} fix(es); "
                f"validation rounds {[len(p) for p in problems]}; dry run {dry.get('status')} "
                f"({sum(s['status'] == 'ok' for s in dry.get('trace', []))}/{len(dry.get('trace', []))} steps ok)"
            )
            ok &= built
            if not built:
                continue
            service.deploy(wid)
            trigger = wf["workflow"]["trigger"]
            if trigger["type"] == "file":
                for sample in sorted((settings.fixtures / "samples").glob(trigger["pattern"] or "*")):
                    service.drop(sample.name, sample.read_bytes())
            fired = await service.tick()
            runs = service.store.runs(wid)
            passed = fired > 0 and all(r["status"] == "succeeded" for r in runs)
            ok &= passed
            print(f"      live: {fired} run(s) fired, {sum(r['status'] == 'succeeded' for r in runs)} succeeded")
            if verbose:
                for r in runs:
                    for s in r["trace"]:
                        print(f"        {s['status']:>8}  {s['id']}  {s.get('reason') or s.get('error') or ''}")
        ws = service.workspace()
        print(
            f"\nWorkspace: {len(ws['ledger'])} ledger rows, {len(ws['outbox'])} drafts in the outbox, "
            f"{len(ws['notifications'])} notifications, {len(ws['inbox'])} files left in the inbox"
        )
        ok &= not ws["inbox"]
        ok &= not service.store.alerts()
        print(f"Alerts raised: {len(service.store.alerts())}")
    finally:
        await service.stop()
        shutil.rmtree(settings.data_dir, ignore_errors=True)
    return ok
