"""Model layer: structured outputs for the analyst and designer, and typed extraction for llm steps."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, Field, create_model

from .config import Settings
from .spec import OutputField

T = TypeVar("T", bound=BaseModel)
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMRefusal(RuntimeError):
    pass


class Analysis(BaseModel):
    process: str = Field(description="A short name for the process.")
    goal: str = Field(description="What the automation achieves, in one sentence.")
    trigger: str = Field(description="What starts it: a schedule, a new file, or a person.")
    steps: list[str] = Field(description="The process in plain steps, in order.")
    rules: list[str] = Field(description="Business rules and thresholds, stated precisely.")
    systems: list[str] = Field(description="Systems or data involved.")
    assumptions: list[str] = Field(description="Assumptions made where the description was unclear.")


class LLM(Protocol):
    async def structured(self, system: str, prompt: str, schema: type[T], effort: str) -> T: ...

    async def extract(self, instruction: str, text: str, fields: list[OutputField]) -> dict: ...


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    def tighten(node: Any) -> Any:
        if isinstance(node, dict):
            node = {k: tighten(v) for k, v in node.items() if k not in ("title", "default")}
            if node.get("type") == "object" and "properties" in node:
                node["required"] = list(node["properties"])
                node["additionalProperties"] = False
        elif isinstance(node, list):
            node = [tighten(v) for v in node]
        return node

    schema = model.model_json_schema()
    defs = schema.pop("$defs", None)
    schema = tighten(schema)
    if defs:
        schema["$defs"] = {k: tighten(v) for k, v in defs.items()}
    return schema


def field_model(fields: list[OutputField]) -> type[BaseModel]:
    """A Pydantic model built from an llm step's declared fields, so its output is schema-checked too."""
    types = {"string": str, "number": float, "boolean": bool}
    return create_model("Extracted", **{f.name: (types[f.type], Field(description=f.description)) for f in fields})


EXTRACT_SYSTEM = """You are one step inside an automated workflow. Read the input and return exactly the requested fields.
Use only what the input says. For a number, return the plain number (no currency symbols or commas). If a value is
genuinely absent, return an empty string, 0 or false."""


class AnthropicLLM:
    def __init__(self, settings: Settings) -> None:
        import anthropic

        self.client = anthropic.AsyncAnthropic()
        self.model = settings.model
        self.settings = settings

    async def structured(self, system: str, prompt: str, schema: type[T], effort: str) -> T:
        response = await self.client.beta.messages.create(
            model=self.model,
            max_tokens=12000,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": strict_schema(schema)}},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            raise LLMRefusal("Claude declined this request.")
        return schema.model_validate(json.loads(next(b.text for b in response.content if b.type == "text")))

    async def extract(self, instruction: str, text: str, fields: list[OutputField]) -> dict:
        model = field_model(fields)
        result = await self.structured(
            EXTRACT_SYSTEM, f"{instruction}\n\n<input>\n{text}\n</input>", model, self.settings.step_effort
        )
        return result.model_dump()


# ── scripted model ──
MONEY = re.compile(r"(?:[$£€]|USD|SGD|GBP|EUR)\s?([\d,]+(?:\.\d{2})?)|([\d,]+\.\d{2})")
DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2} [A-Z][a-z]{2,8} \d{4})\b")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


class ScriptedLLM:
    """Deterministic stand-in. It recognises a few common process shapes and designs them from the real registry."""

    def __init__(self, delay: float = 0.0, flawed_first_draft: bool = True) -> None:
        self.delay = delay
        # The first design misnames one tool argument, the kind of slip the validator exists to catch.
        self.flawed_first_draft = flawed_first_draft

    async def _pause(self, k: float = 1) -> None:
        if self.delay:
            await asyncio.sleep(self.delay * k)

    async def structured(self, system: str, prompt: str, schema: type[T], effort: str) -> T:
        await self._pause(20)
        from .spec import Workflow

        if schema is Analysis:
            return schema.model_validate(self._analyse(prompt))
        if schema is Workflow:
            return schema.model_validate(self._design(prompt))
        raise ValueError(f"ScriptedLLM has no script for {schema.__name__}")

    @staticmethod
    def _kind(text: str) -> str:
        t = text.lower()
        if "invoice" in t:
            return "invoice"
        if "overdue" in t or "task" in t:
            return "digest"
        return "generic"

    def _analyse(self, prompt: str) -> dict:
        desc = prompt.split("<description>")[-1].split("</description>")[0].strip()
        threshold = re.search(r"(?:over|above|more than)\s*[$£€]?\s?([\d,]+)", desc)
        kind = self._kind(desc)
        if kind == "invoice":
            return {
                "process": "Invoice intake",
                "goal": "Log every incoming invoice, route large ones for approval and acknowledge receipt.",
                "trigger": "A new invoice file arrives in the inbox folder.",
                "steps": [
                    "Read the new invoice",
                    "Extract vendor, amount, due date and contact email",
                    "Add it to the ledger",
                    "If the amount is large, alert finance",
                    "Email the vendor to confirm receipt",
                    "Move the file to processed",
                ],
                "rules": [f"Invoices over {threshold.group(1) if threshold else '5,000'} need finance approval"],
                "systems": ["inbox folder", "ledger.csv", "#finance channel", "email"],
                "assumptions": ["Invoices are plain-text files", "The vendor's email appears on the invoice"],
            }
        if kind == "digest":
            return {
                "process": "Overdue task digest",
                "goal": "Tell the team which tasks are overdue, on a schedule.",
                "trigger": "A schedule, every few minutes in the demo.",
                "steps": [
                    "Read the task tracker",
                    "Keep tasks that are overdue",
                    "Summarise them",
                    "Post the digest to the team channel",
                ],
                "rules": ["A task is overdue when status is overdue"],
                "systems": ["tasks.csv", "#team channel"],
                "assumptions": ["The tracker has a status column"],
            }
        return {
            "process": "Document notice",
            "goal": "Summarise new documents for the team.",
            "trigger": "A new file in the inbox.",
            "steps": ["Read the new file", "Summarise it", "Post the summary"],
            "rules": [],
            "systems": ["inbox", "#team"],
            "assumptions": [],
        }

    def _design(self, prompt: str) -> dict:
        revising = "<problems>" in prompt
        flaw = self.flawed_first_draft and not revising
        threshold = re.search(r"over ([\d,]+)", prompt)
        limit = (threshold.group(1) if threshold else "5000").replace(",", "")
        kind = self._kind(prompt.split("<analysis>")[-1])
        none = None

        def tool(id_, title, tool_id, args, when=none):
            return {
                "id": id_,
                "title": title,
                "kind": "tool",
                "tool": tool_id,
                "args": [{"name": k, "value": v} for k, v in args.items()],
                "instruction": "",
                "input": "",
                "fields": [],
                "when": when,
            }

        def llm(id_, title, instruction, input_, fields):
            return {
                "id": id_,
                "title": title,
                "kind": "llm",
                "tool": "",
                "args": [],
                "instruction": instruction,
                "input": input_,
                "fields": [{"name": n, "type": t, "description": d} for n, t, d in fields],
                "when": None,
            }

        message_arg = "message" if flaw else "text"
        if kind == "invoice":
            steps = [
                tool("read", "Read the invoice", "files.read_file", {"path": "{{trigger.file}}"}),
                llm(
                    "extract",
                    "Pull out the key fields",
                    "Extract the invoice details.",
                    "{{steps.read.content}}",
                    [
                        ("vendor", "string", "Vendor company name"),
                        ("invoice_number", "string", "Invoice number"),
                        ("amount", "number", "Total amount due"),
                        ("due_date", "string", "Due date, as written"),
                        ("email", "string", "Vendor contact email"),
                    ],
                ),
                tool(
                    "log",
                    "Add to the ledger",
                    "sheets.append_row",
                    {
                        "path": "ledger.csv",
                        "row": '{"vendor": "{{steps.extract.vendor}}", "invoice": "{{steps.extract.invoice_number}}", "amount": "{{steps.extract.amount}}", "due": "{{steps.extract.due_date}}", "file": "{{steps.read.name}}"}',
                    },
                ),
                tool(
                    "alert",
                    "Flag for approval",
                    "notify.post_message",
                    {
                        "channel": "#finance",
                        message_arg: "Invoice {{steps.extract.invoice_number}} from {{steps.extract.vendor}} for {{steps.extract.amount}} needs approval.",
                        "level": "urgent",
                    },
                    {"left": "{{steps.extract.amount}}", "op": "gt", "right": limit},
                ),
                tool(
                    "ack",
                    "Confirm receipt",
                    "mail.draft_email",
                    {
                        "to": "{{steps.extract.email}}",
                        "subject": "Received: invoice {{steps.extract.invoice_number}}",
                        "body": "Hello {{steps.extract.vendor}},\n\nWe've received invoice {{steps.extract.invoice_number}} and logged it for payment by {{steps.extract.due_date}}.\n\nAccounts payable",
                    },
                    {"left": "{{steps.extract.email}}", "op": "exists", "right": ""},
                ),
                tool(
                    "file", "Move to processed", "files.move_file", {"path": "{{trigger.file}}", "folder": "processed"}
                ),
            ]
            return {
                "name": "invoice-intake",
                "summary": "Logs each new invoice, flags big ones for finance and confirms receipt with the vendor.",
                "trigger": {"type": "file", "every_minutes": 0, "folder": "inbox", "pattern": "*.txt"},
                "steps": steps,
            }
        if kind == "digest":
            steps = [
                tool(
                    "overdue",
                    "Find overdue tasks",
                    "sheets.filter_rows",
                    {"path": "tasks.csv", "column": "status", "op": "eq", "value": "overdue"},
                ),
                llm(
                    "summary",
                    "Write the digest",
                    "Summarise the overdue tasks for the team.",
                    "{{steps.overdue.rows}}",
                    [("headline", "string", "One-line headline"), ("count", "number", "How many tasks are overdue")],
                ),
                tool(
                    "post",
                    "Post to the team",
                    "notify.post_message",
                    {"channel": "#team", message_arg: "{{steps.summary.headline}}", "level": "warning"},
                    {"left": "{{steps.overdue.count}}", "op": "gt", "right": "0"},
                ),
            ]
            return {
                "name": "overdue-digest",
                "summary": "Posts a digest of overdue tasks to the team channel on a schedule.",
                "trigger": {"type": "schedule", "every_minutes": 1, "folder": "", "pattern": ""},
                "steps": steps,
            }
        steps = [
            tool("read", "Read the file", "files.read_file", {"path": "{{trigger.file}}"}),
            llm(
                "summary",
                "Summarise it",
                "Summarise the document in one line.",
                "{{steps.read.content}}",
                [("headline", "string", "One-line summary")],
            ),
            tool(
                "post",
                "Tell the team",
                "notify.post_message",
                {"channel": "#team", message_arg: "New file {{steps.read.name}}: {{steps.summary.headline}}"},
            ),
        ]
        return {
            "name": "document-notice",
            "summary": "Summarises new files and tells the team.",
            "trigger": {"type": "file", "every_minutes": 0, "folder": "inbox", "pattern": "*"},
            "steps": steps,
        }

    async def extract(self, instruction: str, text: str, fields: list[OutputField]) -> dict:
        await self._pause(10)
        out: dict = {}
        aliases = {
            "invoice_number": r"invoice\s*(?:#|no\.?|number)",
            "due_date": r"due(?:\s*date)?",
            "email": r"(?:e-?mail|contact)",
        }
        for f in fields:
            label = aliases.get(f.name, f.name.replace("_", "[ _]?"))
            labelled = re.search(rf"^\s*{label}\s*:?\s*[:#]?\s*(.+)$", text, re.I | re.M)
            if f.type == "number":
                if f.name == "count":
                    out[f.name] = float(text.count("'title'") or text.count('"title"'))
                    continue
                amounts = [float((a or b).replace(",", "")) for a, b in MONEY.findall(text)]
                total = re.search(r"total[^\n\d]*([\d,]+(?:\.\d{2})?)", text, re.I)
                out[f.name] = float(total.group(1).replace(",", "")) if total else max(amounts, default=0.0)
            elif f.type == "boolean":
                out[f.name] = bool(labelled)
            elif labelled:
                out[f.name] = labelled.group(1).strip()
            elif "email" in f.name:
                m = EMAIL.search(text)
                out[f.name] = m.group(0) if m else ""
            elif "date" in f.name or "due" in f.name:
                m = DATE.search(text)
                out[f.name] = m.group(1) if m else ""
            elif f.name in ("vendor", "from", "company"):
                m = re.search(r"^\s*(?:from|vendor|bill from)\s*:\s*(.+)$", text, re.I | re.M)
                out[f.name] = m.group(1).strip() if m else text.strip().splitlines()[0][:60]
            elif f.name == "headline":
                titles = re.findall(r"'title': '([^']+)'|\"title\": \"([^\"]+)\"", text)
                names = [a or b for a, b in titles]
                out[f.name] = (
                    f"{len(names)} overdue: {', '.join(names)}" if names else text.strip().splitlines()[0][:120]
                )
            else:
                out[f.name] = ""
        return out


def make_llm(settings: Settings) -> LLM:
    if settings.llm == "scripted":
        return ScriptedLLM(delay=settings.scripted_delay)
    if settings.llm == "anthropic":
        return AnthropicLLM(settings)
    raise ValueError(f"Unknown LLM backend: {settings.llm}")
