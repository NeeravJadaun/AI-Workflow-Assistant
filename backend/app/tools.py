"""Read-only tools exposed to the agent. No writes, no arbitrary SQL, no external calls."""
import re

from . import db, policy

STOPWORDS = {"the", "and", "for", "that", "this", "with", "have", "from", "again", "since", "there", "cannot", "will", "not"}


def lookup_policy(query: str) -> list[dict]:
    return [
        {"id": p.id, "title": p.title, "urgency": p.urgency, "category": p.category, "rule": p.rule}
        for p in policy.lookup_policy(query)
    ]


def search_requests(text: str, exclude_id: int | None = None, limit: int = 5) -> list[dict]:
    """Find existing requests sharing keywords. Parameterised SQL on a read-only connection."""
    words = sorted({w for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in STOPWORDS})[:8]
    if not words:
        return []
    clause = " OR ".join("lower(description) LIKE ?" for _ in words)
    params = [f"%{w}%" for w in words]
    sql = f"SELECT id, unit, status, description FROM requests WHERE ({clause})"
    if exclude_id is not None:
        sql += " AND id != ?"
        params.append(exclude_id)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    conn = db.connect_readonly()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    return [{"id": r["id"], "unit": r["unit"], "status": r["status"], "description": r["description"][:120]} for r in rows]
