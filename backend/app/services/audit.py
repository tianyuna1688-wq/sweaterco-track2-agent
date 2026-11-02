"""Local single-user audit store. Parameterized SQL; request-scoped checkpoints."""

import json
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parents[2]


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connection():
    path = Path(os.getenv("AUDIT_DB_PATH", str(ROOT / "runtime" / "audit.sqlite3")))
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(
        "CREATE TABLE IF NOT EXISTS audit (request_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL)"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS checkpoints (session_id TEXT PRIMARY KEY, updated_at TEXT NOT NULL, payload TEXT NOT NULL)"
    )
    try:
        yield con
        con.commit()
    finally:
        con.close()


def save_result(result, message):
    record = {**result, "input": message}
    with connection() as con:
        con.execute(
            "INSERT INTO audit VALUES (?,?,?,?)",
            (
                result["request_id"],
                result["session_id"],
                result["created_at"],
                json.dumps(record, ensure_ascii=False),
            ),
        )
        if result["status"] == "clarification":
            con.execute(
                "INSERT OR REPLACE INTO checkpoints VALUES (?,?,?)",
                (result["session_id"], now(), json.dumps(result, ensure_ascii=False)),
            )
        else:
            con.execute(
                "DELETE FROM checkpoints WHERE session_id=?", (result["session_id"],)
            )


def checkpoint(session_id):
    if not session_id:
        return None
    with connection() as con:
        row = con.execute(
            "SELECT payload, updated_at FROM checkpoints WHERE session_id=?",
            (session_id,),
        ).fetchone()
        if row and datetime.fromisoformat(row["updated_at"]) > datetime.now(
            timezone.utc
        ) - timedelta(hours=24):
            return json.loads(row["payload"])
        con.execute("DELETE FROM checkpoints WHERE session_id=?", (session_id,))
    return None


def history(limit=100):
    with connection() as con:
        rows = con.execute(
            "SELECT payload FROM audit ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [json.loads(r["payload"]) for r in rows]


def get_record(request_id):
    with connection() as con:
        row = con.execute(
            "SELECT payload FROM audit WHERE request_id=?", (request_id,)
        ).fetchone()
    return json.loads(row["payload"]) if row else None
