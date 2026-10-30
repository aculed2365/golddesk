"""Tiny SQLite log: every alert, every agent's answer, every call."""
import json
import sqlite3
import threading
from datetime import datetime

import config

_lock = threading.Lock()
_conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row
_conn.executescript(
    """
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT, alert TEXT, status TEXT, grade TEXT, call TEXT
);
CREATE TABLE IF NOT EXISTS agent_notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER, agent TEXT, output TEXT, ts TEXT
);
CREATE TABLE IF NOT EXISTS radar (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, output TEXT
);
CREATE TABLE IF NOT EXISTS seen (key TEXT PRIMARY KEY, ts TEXT);
CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT);
"""
)
_conn.commit()


def _now():
    return datetime.now(config.DUBAI).strftime("%Y-%m-%d %H:%M:%S")


def new_run(alert: dict) -> int:
    with _lock:
        cur = _conn.execute(
            "INSERT INTO runs (ts, alert, status) VALUES (?,?,?)",
            (_now(), json.dumps(alert), "running"),
        )
        _conn.commit()
        return cur.lastrowid


def note(run_id: int, agent: str, output) -> None:
    with _lock:
        _conn.execute(
            "INSERT INTO agent_notes (run_id, agent, output, ts) VALUES (?,?,?,?)",
            (run_id, agent, json.dumps(output), _now()),
        )
        _conn.commit()


def finish(run_id: int, status: str, grade: str = "", call: str = "") -> None:
    with _lock:
        _conn.execute(
            "UPDATE runs SET status=?, grade=?, call=? WHERE id=?",
            (status, grade, call, run_id),
        )
        _conn.commit()


def runs_last_hour() -> int:
    with _lock:
        r = _conn.execute(
            "SELECT COUNT(*) FROM runs WHERE ts >= datetime(?, '-1 hour')", (_now(),)
        ).fetchone()
        return r[0]


def recent_runs(limit: int = 30) -> list:
    with _lock:
        rows = _conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        out = []
        for r in rows:
            notes = _conn.execute(
                "SELECT agent, output FROM agent_notes WHERE run_id=? ORDER BY id", (r["id"],)
            ).fetchall()
            d = dict(r)
            d["alert"] = json.loads(d["alert"] or "{}")
            d["notes"] = {n["agent"]: json.loads(n["output"]) for n in notes}
            out.append(d)
        return out


def runs_since(ts: str) -> list:
    with _lock:
        return [dict(r) for r in _conn.execute(
            "SELECT * FROM runs WHERE ts >= ? ORDER BY id", (ts,)
        ).fetchall()]


def save_radar(output: dict) -> None:
    with _lock:
        _conn.execute("INSERT INTO radar (ts, output) VALUES (?,?)", (_now(), json.dumps(output)))
        _conn.commit()


def seen_before(key: str) -> bool:
    """True if key was already recorded; records it if not."""
    with _lock:
        if _conn.execute("SELECT 1 FROM seen WHERE key=?", (key,)).fetchone():
            return True
        _conn.execute("INSERT INTO seen (key, ts) VALUES (?,?)", (key, _now()))
        _conn.commit()
        return False


def get_state(key: str, default: str = "") -> str:
    with _lock:
        r = _conn.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return r[0] if r else default


def set_state(key: str, value: str) -> None:
    with _lock:
        _conn.execute(
            "INSERT INTO state (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        _conn.commit()
