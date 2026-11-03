"""The builder: a LangGraph loop that turns a plain-language description into a tested workflow.

analyse ──> design ──> validate ──┬─(problems)──> design (fix)
                                  └─> dry_run ──┬─(failed)──> design (fix)
                                                └─> ready
"""

from __future__ import annotations

import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from .config import Settings
from .engine import execute
from .hub import ToolHub
from .llm import LLM, Analysis
from .spec import Workflow, validate

STYLE = "British spelling. Never use em dashes; use a plain hyphen."

ANALYST = f"""You are a process analyst. Someone describes a business process in their own words. Restate it precisely:
the goal, what triggers it, the steps in order, every business rule with exact thresholds, the systems and data
involved, and the assumptions you had to make. Do not invent requirements. {STYLE}"""

DESIGNER = f"""You are an automation designer. Turn a process analysis into a workflow that runs on the tools in the registry.
- Use only registry tools, with exactly their argument names. Workspace paths are relative, e.g. inbox/x.txt, ledger.csv.
- Pass data between steps with templates: {{{{trigger.file}}}} (the file that started a file-triggered run), {{{{steps.<id>.<field>}}}}.
- Use an llm step to read unstructured text and return typed fields; then later steps can use those fields.
- Put business rules in `when` conditions on the steps they gate (e.g. only alert when amount gt 5000).
- Prefer drafting emails and posting notifications over anything irreversible. Move processed files so they aren't handled twice.
- For object arguments, give a JSON object whose values are templates or literals. {STYLE}"""


class BuildState(TypedDict, total=False):
    description: str
    analysis: dict
    workflow: dict
    problems: list[str]
    dry_run: dict
    fixes: int
    status: str


def emit(**event) -> None:
    get_stream_writer()(event)


@dataclass
class Builder:
    llm: LLM
    settings: Settings
    registry: str  # the live tool registry, as the designer sees it
    tools: dict

    def build(self):
        g = StateGraph(BuildState)
        g.add_node("analyse", self.analyse)
        g.add_node("design", self.design)
        g.add_node("validate", self.check)
        g.add_node("dry_run", self.dry_run)
        g.add_edge(START, "analyse")
        g.add_edge("analyse", "design")
        g.add_edge("design", "validate")
        g.add_conditional_edges("validate", self.after_validate, {"design": "design", "dry_run": "dry_run", "end": END})
        g.add_conditional_edges("dry_run", self.after_dry_run, {"design": "design", "end": END})
        return g.compile()

    async def analyse(self, state: BuildState) -> BuildState:
        emit(type="stage", stage="analyse", status="running")
        t0 = time.perf_counter()
        analysis = await self.llm.structured(
            ANALYST, f"<description>\n{state['description']}\n</description>", Analysis, self.settings.analyse_effort
        )
        emit(type="analysis", analysis=analysis.model_dump(), ms=round((time.perf_counter() - t0) * 1000))
        return {"analysis": analysis.model_dump(), "fixes": 0, "problems": []}

    async def design(self, state: BuildState) -> BuildState:
        fixing = bool(state.get("problems"))
        emit(type="stage", stage="fix" if fixing else "design", status="running", attempt=state.get("fixes", 0) + 1)
        prompt = f"<registry>\n{self.registry}\n</registry>\n\n<analysis>\n{state['analysis']}\n</analysis>"
        if fixing:
            problems = "\n".join(f"- {p}" for p in state["problems"])
            prompt += f"\n\n<current_workflow>\n{state['workflow']}\n</current_workflow>\n\n<problems>\n{problems}\n</problems>\nFix every problem; keep what works."
        wf = await self.llm.structured(DESIGNER, prompt, Workflow, self.settings.design_effort)
        emit(type="workflow", workflow=wf.model_dump())
        return {"workflow": wf.model_dump(), "fixes": state.get("fixes", 0) + (1 if fixing else 0)}

    async def check(self, state: BuildState) -> BuildState:
        problems = validate(Workflow.model_validate(state["workflow"]), self.tools)
        emit(type="validation", problems=problems)
        return {"problems": problems}

    def after_validate(self, state: BuildState) -> str:
        if not state["problems"]:
            return "dry_run"
        return "design" if state["fixes"] < self.settings.max_fixes else "end"

    async def dry_run(self, state: BuildState) -> BuildState:
        """Run against a throwaway copy of the workspace, through its own MCP servers."""
        emit(type="stage", stage="dry_run", status="running")
        wf = Workflow.model_validate(state["workflow"])
        sandbox = Path(tempfile.mkdtemp(prefix="flowmind-sandbox-"))
        try:
            shutil.copytree(self.settings.workspace, sandbox, dirs_exist_ok=True)
            trigger = sample_trigger(wf, sandbox, self.settings.fixtures)
            async with ToolHub(sandbox) as hub:

                async def on_step(entry: dict) -> None:
                    emit(type="dry_step", step=entry)

                result = await execute(wf, hub, self.llm, trigger, on_step)
        finally:
            shutil.rmtree(sandbox, ignore_errors=True)
        result["trigger"] = trigger
        problems = [f"Dry run failed at {result['error']}"] if result["status"] == "failed" else []
        emit(type="dry_run", result=result)
        return {"dry_run": result, "problems": problems, "status": "ready" if not problems else "needs_work"}

    def after_dry_run(self, state: BuildState) -> str:
        if not state["problems"]:
            return "end"
        return "design" if state["fixes"] < self.settings.max_fixes else "end"


def sample_trigger(wf: Workflow, sandbox: Path, fixtures: Path) -> dict:
    """A realistic trigger for the dry run: a file in the watched folder, or a sample dropped in."""
    if wf.trigger.type != "file":
        return {}
    folder = sandbox / wf.trigger.folder
    folder.mkdir(parents=True, exist_ok=True)
    found = sorted(folder.glob(wf.trigger.pattern or "*"))
    if not found:
        samples = sorted((fixtures / "samples").glob(wf.trigger.pattern or "*"))
        if samples:
            shutil.copy(samples[0], folder / samples[0].name)
            found = [folder / samples[0].name]
    if not found:
        return {"file": f"{wf.trigger.folder}/example.txt", "name": "example.txt"}
    return {"file": found[0].relative_to(sandbox).as_posix(), "name": found[0].name}
