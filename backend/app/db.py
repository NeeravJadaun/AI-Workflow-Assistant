from contextlib import contextmanager
import json
import sqlite3
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, role TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT, unit TEXT NOT NULL, description TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'submitted', created_by TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS proposals (
  id INTEGER PRIMARY KEY AUTOINCREMENT, request_id INTEGER NOT NULL REFERENCES requests(id),
  mode TEXT NOT NULL, urgency TEXT NOT NULL, category TEXT NOT NULL, title TEXT NOT NULL,
  description TEXT NOT NULL, reasoning TEXT NOT NULL, policy_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending', decided_by TEXT, decided_at TEXT,
  reject_reason TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS work_orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  proposal_id INTEGER NOT NULL UNIQUE REFERENCES proposals(id),
  request_id INTEGER NOT NULL REFERENCES requests(id),
  urgency TEXT NOT NULL, category TEXT NOT NULL, title TEXT NOT NULL,
  description TEXT NOT NULL, policy_id TEXT NOT NULL,
  approved_by TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, actor TEXT NOT NULL,
  action TEXT NOT NULL, request_id INTEGER, proposal_id INTEGER, detail TEXT);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def connect_readonly() -> sqlite3.Connection:
    """Read-only connection used by agent tools: writes raise an error."""
    conn = sqlite3.connect(f"file:{config.db_path()}?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with tx() as conn:
        conn.executescript(SCHEMA)


def audit(conn, actor, action, request_id=None, proposal_id=None, detail=None) -> None:
    conn.execute(
        "INSERT INTO audit_log (ts, actor, action, request_id, proposal_id, detail) VALUES (?,?,?,?,?,?)",
        (now(), actor, action, request_id, proposal_id,
         json.dumps(detail) if detail is not None else None),
    )


@contextmanager
def tx():
    """Connection that commits on success, rolls back on error, and always closes."""
    conn = connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()
