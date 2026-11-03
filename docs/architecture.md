# Architecture

## Plan once, execute deterministically

FlowMind uses the model where judgement is needed and code everywhere else:

| Stage | Who decides | How |
|---|---|---|
| Analyse | Claude | Structured output: process, goal, trigger, steps, rules, systems, assumptions |
| Design | Claude | Structured output: a `Workflow` (trigger plus steps) over the live tool registry |
| Validate | Code | Tools exist; required arguments are present; no unknown arguments; templates only reference the trigger or earlier steps; AI-step fields exist |
| Dry run | Code + MCP | Executes the workflow in a sandbox with real tool calls |
| Every live run | Code + MCP | Same engine. Claude is called only inside AI steps, with a schema built from the step's declared fields |

A deployed workflow behaves the same way on its thousandth run as on its first. The model never improvises control flow at run time.

## The workflow language

```json
{
  "name": "invoice-intake",
  "trigger": { "type": "file", "folder": "inbox", "pattern": "*.txt", "every_minutes": 0 },
  "steps": [
    { "id": "read", "kind": "tool", "tool": "files.read_file", "args": [{ "name": "path", "value": "{{trigger.file}}" }] },
    { "id": "extract", "kind": "llm", "instruction": "Extract the invoice details.", "input": "{{steps.read.content}}",
      "fields": [{ "name": "amount", "type": "number", "description": "Total amount due" }, "…"] },
    { "id": "alert", "kind": "tool", "tool": "notify.post_message",
      "args": [{ "name": "channel", "value": "#finance" }, { "name": "text", "value": "Invoice {{steps.extract.invoice_number}} needs approval." }],
      "when": { "left": "{{steps.extract.amount}}", "op": "gt", "right": "5000" } }
  ]
}
```

- **Templates.** A value that is exactly one template keeps the referenced value's type (a number stays a number). Interpolated templates become text, and whole numbers print without a trailing `.0`.
- **Object arguments** (such as a ledger row) are written as JSON whose values may be templates. Substituted values are JSON-escaped, so a vendor called `Acme "Ltd"` can't break the row.
- **Arguments are coerced** to the type the tool's JSON schema declares.
- **Conditions** compare numerically when both sides are numbers (`$5,000` counts), otherwise as text. A condition whose template doesn't resolve is false, except `ne`.

## MCP

`ToolHub` launches each bundled server as `python -m flowmind.servers.<name>` over stdio, calls `initialize`, and builds the registry from `list_tools`: the name, description, `input_schema` and `read_only_hint`. The designer sees the registry as compact signatures:

```
- files.read_file(path: string) [read-only]: Read a text file from the workspace.
- sheets.append_row(path: string, row: object): Append one row to a CSV table, creating it with these columns if it doesn't exist. Unknown columns are rejected.
- notify.post_message(channel: string, text: string, level: string?): Post a message to a team channel such as #finance.
```

Servers raise `ToolError` with specific messages ("Unknown columns ['surprise']. Columns: [...]"), which reach both the designer (during a dry run) and the run trace.

MCP stdio sessions run inside anyio cancel scopes, so each hub is opened and closed in the same task:
- the live hub in the app lifespan
- each sandbox hub inside its dry run
- the test hubs inside each test

## Dry runs

1. Copy the live workspace to a temporary directory.
2. Start a second set of MCP servers with `FLOWMIND_WORKSPACE` pointing at the copy.
3. Pick a realistic trigger: the first matching file in the watched folder, or a bundled sample copied in.
4. Execute, trace, and delete the copy.

A failure becomes a problem for the designer: `Dry run failed at log: Unknown columns [...]`.

## Runner and monitor

The runner wakes every `tick_seconds`:

- **Schedules** run once on deploy, then every N minutes after the last run.
- **Watched folders:** each matching file is claimed with an `INSERT OR IGNORE` on `(workflow, path:mtime)` before it runs, so a file is handled exactly once even if the workflow doesn't move it. A file that's changed counts as new.

After each run, the monitor compares it with the workflow's history and its dry run:

| Alert | Level | Fires when |
|---|---|---|
| failure | error | Any step fails |
| slow | warning | The run takes more than 3× the median of recent successful runs (with at least 5 runs of history) |
| drift | warning | An AI step returns empty for a field the dry run filled in, often the first sign that incoming documents have changed format |

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/workflows` | Describe a process; starts a build |
| `GET /api/workflows/{id}/events` | SSE: stage, analysis, workflow, validation, dry_step, dry_run, done |
| `POST /api/workflows/{id}/rebuild` | Add a note and rebuild |
| `POST /api/workflows/{id}/deploy`, `/pause`, `/run` | Lifecycle (deploy requires a passed dry run) |
| `GET /api/registry` | The live MCP tool registry |
| `GET /api/workspace`, `POST /api/workspace/inbox`, `POST /api/workspace/samples/{name}` | The workspace, and dropping files into the inbox |
| `GET /api/runs`, `GET /api/alerts`, `POST /api/alerts/{id}/ack`, `GET /api/activity` (SSE) | Monitoring |
