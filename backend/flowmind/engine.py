"""Runs a workflow step by step and records a trace of every input, output and decision."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from .hub import ToolError, ToolHub
from .llm import LLM
from .spec import Unresolved, Workflow, coerce, holds, render


async def execute(wf: Workflow, hub: ToolHub, llm: LLM, trigger: dict, emit=None) -> dict:
    started = time.perf_counter()
    ctx: dict = {"trigger": {"time": datetime.now(UTC).isoformat(), **trigger}, "steps": {}}
    trace: list[dict] = []
    status, error = "succeeded", None

    for step in wf.steps:
        entry: dict = {"id": step.id, "title": step.title, "kind": step.kind, "tool": step.tool}
        t0 = time.perf_counter()
        try:
            if step.when and not holds(step.when, ctx):
                entry |= {"status": "skipped", "reason": f"{step.when.left} {step.when.op} {step.when.right}".strip()}
                trace.append(entry)
                if emit:
                    await emit(entry)
                continue
            if step.kind == "tool":
                schema = hub.tools[step.tool].input_schema.get("properties", {})
                args = {a.name: coerce(a.value, schema.get(a.name, {}), ctx) for a in step.args}
                entry["input"] = args
                output, _ = await hub.call(step.tool, args)
            else:
                text = render(step.input, ctx)
                text = text if isinstance(text, str) else str(text)
                entry["input"] = {"text": text[:400]}
                output = await llm.extract(step.instruction, text, step.fields)
            ctx["steps"][step.id] = output
            entry |= {"status": "ok", "output": output}
        except (ToolError, Unresolved, ValueError, KeyError, TypeError) as exc:
            message = f"Template {{{{{exc.args[0]}}}}} didn't resolve." if isinstance(exc, Unresolved) else str(exc)
            entry |= {"status": "failed", "error": message}
            status, error = "failed", f"{step.id}: {message}"
        entry["ms"] = round((time.perf_counter() - t0) * 1000)
        trace.append(entry)
        if emit:
            await emit(entry)
        if status == "failed":
            break

    return {"status": status, "error": error, "trace": trace, "ms": round((time.perf_counter() - started) * 1000)}
