"""MCP server: CSV tables in the workspace (ledgers, trackers, lists)."""

from __future__ import annotations

import csv

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from ._workspace import inside, rel

server = MCPServer("sheets", instructions="Read, filter and append rows in CSV tables inside the FlowMind workspace.")
OPS = {"eq", "ne", "gt", "lt", "gte", "lte", "contains"}


def _load(path: str) -> tuple[list[str], list[dict]]:
    target = inside(path)
    if not target.is_file():
        raise ToolError(f"No table '{path}'.")
    with target.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def _num(v):
    try:
        return float(str(v).replace(",", "").replace("$", ""))
    except ValueError:
        return None


@server.tool(annotations=ToolAnnotations(read_only_hint=True))
def read_table(path: str) -> dict:
    """Read every row of a CSV table."""
    columns, rows = _load(path)
    return {"columns": columns, "rows": rows, "count": len(rows)}


@server.tool(annotations=ToolAnnotations(read_only_hint=True))
def filter_rows(path: str, column: str, op: str, value: str) -> dict:
    """Rows where `column` compares to `value`. op is one of eq, ne, gt, lt, gte, lte, contains."""
    if op not in OPS:
        raise ToolError(f"op must be one of {sorted(OPS)}.")
    columns, rows = _load(path)
    if column not in columns:
        raise ToolError(f"No column '{column}'. Columns: {columns}.")

    def keep(row: dict) -> bool:
        a, b = row.get(column, ""), value
        if op == "contains":
            return b.lower() in a.lower()
        na, nb = _num(a), _num(b)
        x, y = (na, nb) if na is not None and nb is not None else (a, b)
        return {"eq": x == y, "ne": x != y, "gt": x > y, "lt": x < y, "gte": x >= y, "lte": x <= y}[op]

    hits = [r for r in rows if keep(r)]
    return {"rows": hits, "count": len(hits)}


@server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False))
def append_row(path: str, row: dict) -> dict:
    """Append one row to a CSV table, creating it with these columns if it doesn't exist. Unknown columns are rejected."""
    target = inside(path)
    if not row:
        raise ToolError("row is empty.")
    if target.exists():
        columns, _ = _load(path)
        extra = set(row) - set(columns)
        if extra:
            raise ToolError(f"Unknown columns {sorted(extra)}. Columns: {columns}.")
    else:
        columns = list(row)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(columns)
    with target.open("a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=columns).writerow({c: row.get(c, "") for c in columns})
    _, rows = _load(path)
    return {"path": rel(target), "count": len(rows)}


if __name__ == "__main__":
    server.run()
