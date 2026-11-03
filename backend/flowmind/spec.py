"""The workflow language: steps that call MCP tools or ask the model, wired together with {{templates}}."""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from .hub import ToolInfo

Op = Literal["eq", "ne", "gt", "lt", "gte", "lte", "contains", "exists"]


class Condition(BaseModel):
    left: str = Field(description="A {{template}}, e.g. {{steps.extract.amount}}.")
    op: Op
    right: str = Field(description="The value to compare with; empty for exists.")


class Arg(BaseModel):
    name: str
    value: str = Field(
        description="A literal, a {{template}}, or for object arguments a JSON object whose values may be templates, "
        'e.g. {"vendor": "{{steps.extract.vendor}}"}.'
    )


class OutputField(BaseModel):
    name: str = Field(description="snake_case field name.")
    type: Literal["string", "number", "boolean"]
    description: str


class Step(BaseModel):
    id: str = Field(description="Short snake_case id, unique in the workflow.")
    title: str = Field(description="What this step does, in a few words.")
    kind: Literal["tool", "llm"]
    tool: str = Field(description="For tool steps: server.tool from the registry. Empty for llm steps.")
    args: list[Arg] = Field(description="For tool steps: one entry per argument. Empty for llm steps.")
    instruction: str = Field(description="For llm steps: what to work out from the input. Empty for tool steps.")
    input: str = Field(description="For llm steps: a {{template}} with the text to read. Empty for tool steps.")
    fields: list[OutputField] = Field(description="For llm steps: the fields to return. Empty for tool steps.")
    when: Condition | None = Field(description="Run this step only if the condition holds; null to always run.")


class Trigger(BaseModel):
    type: Literal["manual", "schedule", "file"]
    every_minutes: int = Field(description="For schedule triggers; 0 otherwise.")
    folder: str = Field(description="For file triggers: the workspace folder to watch, e.g. inbox. Empty otherwise.")
    pattern: str = Field(description="For file triggers: a glob such as *.txt. Empty otherwise.")


class Workflow(BaseModel):
    name: str
    summary: str = Field(description="One sentence a non-engineer would understand.")
    trigger: Trigger
    steps: list[Step]


TEMPLATE = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")
TRIGGER_KEYS = {"file", "time", "name"}


class Unresolved(KeyError):
    pass


def lookup(path: str, ctx: dict) -> Any:
    node: Any = ctx
    for part in path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            raise Unresolved(path)
    return node


def render(value: str, ctx: dict, json_escape: bool = False) -> Any:
    """Resolve templates. A value that is exactly one template keeps the referenced value's type."""
    whole = TEMPLATE.fullmatch(value.strip())
    if whole and not json_escape:
        return lookup(whole.group(1), ctx)

    def sub(m: re.Match) -> str:
        v = lookup(m.group(1), ctx)
        if isinstance(v, float) and v.is_integer():
            v = int(v)  # 10450.0 reads as 10450 in messages and tables
        text = v if isinstance(v, str) else json.dumps(v)
        return json.dumps(text)[1:-1] if json_escape else text

    return TEMPLATE.sub(sub, value)


def coerce(value: str, schema: dict, ctx: dict) -> Any:
    """Turn an Arg's string value into what the tool's JSON schema expects."""
    kind = schema.get("type")
    if kind in ("object", "array"):
        rendered = render(value, ctx, json_escape=not TEMPLATE.fullmatch(value.strip()))
        return json.loads(rendered) if isinstance(rendered, str) else rendered
    v = render(value, ctx)
    if kind == "integer":
        return int(float(v))
    if kind == "number":
        return float(v)
    if kind == "boolean":
        return v if isinstance(v, bool) else str(v).lower() in ("true", "1", "yes")
    return v if isinstance(v, str) else json.dumps(v)


def validate(wf: Workflow, tools: dict[str, ToolInfo]) -> list[str]:
    """Static checks before anything runs. Returns human-readable problems for the designer to fix."""
    problems: list[str] = []
    seen: dict[str, Step] = {}
    if not wf.steps:
        problems.append("The workflow has no steps.")
    if wf.trigger.type == "file" and not wf.trigger.folder:
        problems.append("A file trigger needs a folder to watch.")
    if wf.trigger.type == "schedule" and wf.trigger.every_minutes < 1:
        problems.append("A schedule trigger needs every_minutes of at least 1.")

    def check_refs(text: str, where: str) -> None:
        for ref in TEMPLATE.findall(text):
            head, _, rest = ref.partition(".")
            if head == "trigger":
                if rest.split(".")[0] not in TRIGGER_KEYS:
                    problems.append(f"{where}: {{{{{ref}}}}} - the trigger only provides {sorted(TRIGGER_KEYS)}.")
            elif head == "steps":
                sid, _, field = rest.partition(".")
                if sid not in seen:
                    problems.append(f"{where}: {{{{{ref}}}}} refers to step '{sid}', which hasn't run yet.")
                elif seen[sid].kind == "llm" and field.split(".")[0] not in {f.name for f in seen[sid].fields}:
                    problems.append(
                        f"{where}: step '{sid}' returns {[f.name for f in seen[sid].fields]}, not '{field}'."
                    )
            else:
                problems.append(f"{where}: {{{{{ref}}}}} must start with trigger. or steps.")

    for step in wf.steps:
        where = f"Step '{step.id}'"
        if step.id in seen:
            problems.append(f"{where}: duplicate id.")
        if step.when:
            check_refs(step.when.left, where)
            check_refs(step.when.right, where)
        if step.kind == "tool":
            tool = tools.get(step.tool)
            if not tool:
                problems.append(f"{where}: unknown tool '{step.tool}'. Use one from the registry.")
            else:
                props = tool.input_schema.get("properties", {})
                given = {a.name for a in step.args}
                for missing in set(tool.input_schema.get("required", [])) - given:
                    problems.append(f"{where}: {step.tool} needs argument '{missing}'.")
                for unknown in given - set(props):
                    problems.append(f"{where}: {step.tool} has no argument '{unknown}'. It takes {sorted(props)}.")
            for a in step.args:
                check_refs(a.value, where)
        else:
            if not step.fields:
                problems.append(f"{where}: an llm step must declare the fields it returns.")
            if not step.input:
                problems.append(f"{where}: an llm step needs an input template.")
            check_refs(step.input, where)
        seen[step.id] = step
    return problems


def holds(cond: Condition, ctx: dict) -> bool:
    try:
        left = render(cond.left, ctx)
    except Unresolved:
        return cond.op == "ne"
    if cond.op == "exists":
        return left not in (None, "", [], {})
    right = render(cond.right, ctx) if cond.right else ""

    def num(v):
        try:
            return float(str(v).replace(",", "").replace("$", ""))
        except ValueError:
            return None

    a, b = num(left), num(right)
    if cond.op in ("gt", "lt", "gte", "lte"):
        if a is None or b is None:
            return False
        return {"gt": a > b, "lt": a < b, "gte": a >= b, "lte": a <= b}[cond.op]
    if cond.op == "contains":
        return str(right).lower() in str(left).lower()
    same = (a == b) if a is not None and b is not None else str(left).strip().lower() == str(right).strip().lower()
    return same if cond.op == "eq" else not same
