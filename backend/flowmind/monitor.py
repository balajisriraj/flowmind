"""Checks every live run against the workflow's own history and its dry run."""

from __future__ import annotations

from statistics import median


def check(run: dict, history: list[dict], dry_run: dict | None) -> list[tuple[str, str]]:
    """Returns (level, message) alerts for one finished run."""
    alerts: list[tuple[str, str]] = []
    if run["status"] == "failed":
        alerts.append(("error", f"Run failed at {run['error']}"))
        return alerts

    # Slow: well beyond the typical duration of recent successful runs.
    times = [r["ms"] for r in history if r["status"] == "succeeded"][:10]
    if len(times) >= 5 and run["ms"] > max(3 * median(times), median(times) + 2000):
        alerts.append(("warning", f"Took {run['ms']} ms, against a typical {round(median(times))} ms."))

    # Drift: a field the dry run filled in comes back empty in production.
    baseline = {s["id"]: s.get("output") or {} for s in (dry_run or {}).get("trace", []) if s.get("kind") == "llm"}
    for step in run["trace"]:
        if step.get("kind") != "llm" or step.get("status") != "ok":
            continue
        for field, expected in baseline.get(step["id"], {}).items():
            got = (step.get("output") or {}).get(field)
            if expected not in ("", 0, None, False) and got in ("", 0, None):
                alerts.append(("warning", f"Extraction drift: '{field}' in step '{step['id']}' came back empty."))
    return alerts
