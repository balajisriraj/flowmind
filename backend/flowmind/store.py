"""SQLite persistence: workflows, runs, alerts and which files a workflow has already handled."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

JSON_COLS = {"analysis", "workflow", "validation", "dry_run", "trigger", "trace"}


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock, self.db:
            self.db.executescript(
                """
                CREATE TABLE IF NOT EXISTS workflows (
                  id TEXT PRIMARY KEY, description TEXT, name TEXT, status TEXT, error TEXT,
                  analysis TEXT, workflow TEXT, validation TEXT, dry_run TEXT, fixes INTEGER DEFAULT 0,
                  created_at TEXT, deployed_at TEXT, last_run_at TEXT);
                CREATE TABLE IF NOT EXISTS runs (
                  id TEXT PRIMARY KEY, workflow_id TEXT, trigger TEXT, status TEXT, error TEXT,
                  trace TEXT, ms INTEGER, started_at TEXT);
                CREATE INDEX IF NOT EXISTS runs_wf ON runs(workflow_id, started_at);
                CREATE TABLE IF NOT EXISTS alerts (
                  id TEXT PRIMARY KEY, workflow_id TEXT, run_id TEXT, level TEXT, message TEXT, at TEXT, acknowledged INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS handled (workflow_id TEXT, key TEXT, PRIMARY KEY (workflow_id, key));
                """
            )

    def _row(self, row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        d = dict(row)
        for k in JSON_COLS & d.keys():
            d[k] = json.loads(d[k]) if d[k] else None
        return d

    def _write(self, sql: str, args: tuple) -> None:
        with self.lock, self.db:
            self.db.execute(sql, args)

    # ── workflows ──
    def create(self, description: str) -> str:
        wid = uuid.uuid4().hex[:10]
        self._write(
            "INSERT INTO workflows(id, description, status, created_at) VALUES (?,?,?,?)",
            (wid, description, "building", now()),
        )
        return wid

    def update(self, wid: str, **fields) -> None:
        cols = {k: json.dumps(v) if k in JSON_COLS else v for k, v in fields.items()}
        self._write(f"UPDATE workflows SET {', '.join(f'{k}=?' for k in cols)} WHERE id=?", (*cols.values(), wid))

    def get(self, wid: str) -> dict | None:
        return self._row(self.db.execute("SELECT * FROM workflows WHERE id=?", (wid,)).fetchone())

    def workflows(self) -> list[dict]:
        rows = self.db.execute("SELECT * FROM workflows ORDER BY created_at DESC").fetchall()
        return [self._row(r) for r in rows]

    def delete(self, wid: str) -> bool:
        with self.lock, self.db:
            for table in ("runs", "alerts", "handled"):
                self.db.execute(f"DELETE FROM {table} WHERE workflow_id=?", (wid,))
            return bool(self.db.execute("DELETE FROM workflows WHERE id=?", (wid,)).rowcount)

    # ── runs and alerts ──
    def add_run(self, wid: str, trigger: dict, result: dict) -> str:
        rid = uuid.uuid4().hex[:10]
        self._write(
            "INSERT INTO runs(id, workflow_id, trigger, status, error, trace, ms, started_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                rid,
                wid,
                json.dumps(trigger),
                result["status"],
                result["error"],
                json.dumps(result["trace"]),
                result["ms"],
                now(),
            ),
        )
        self.update(wid, last_run_at=now())
        return rid

    def runs(self, wid: str | None = None, limit: int = 50) -> list[dict]:
        sql = (
            "SELECT * FROM runs"
            + (" WHERE workflow_id=?" if wid else "")
            + " ORDER BY started_at DESC, rowid DESC LIMIT ?"
        )
        return [self._row(r) for r in self.db.execute(sql, ((wid,) if wid else ()) + (limit,)).fetchall()]

    def alert(self, wid: str, run_id: str, level: str, message: str) -> None:
        self._write(
            "INSERT INTO alerts(id, workflow_id, run_id, level, message, at) VALUES (?,?,?,?,?,?)",
            (uuid.uuid4().hex[:10], wid, run_id, level, message, now()),
        )

    def alerts(self, open_only: bool = False) -> list[dict]:
        sql = (
            "SELECT * FROM alerts"
            + (" WHERE acknowledged=0" if open_only else "")
            + " ORDER BY at DESC, rowid DESC LIMIT 100"
        )
        return [dict(r) for r in self.db.execute(sql).fetchall()]

    def acknowledge(self, aid: str) -> None:
        self._write("UPDATE alerts SET acknowledged=1 WHERE id=?", (aid,))

    # ── file triggers ──
    def claim(self, wid: str, key: str) -> bool:
        """Mark a file as handled by a workflow. False if it already was, so files are never processed twice."""
        with self.lock, self.db:
            return bool(
                self.db.execute("INSERT OR IGNORE INTO handled(workflow_id, key) VALUES (?,?)", (wid, key)).rowcount
            )
