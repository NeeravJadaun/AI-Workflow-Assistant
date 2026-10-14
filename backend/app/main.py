import json
import logging
import sqlite3
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, HTTPException

from . import auth, config, db, models
from .agent import AgentError, run_agent
from .schemas import Edits, LoginIn, RejectIn, RequestIn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("workflow.api")

DEMO_USERS = [("reviewer", "reviewer123", "reviewer"), ("submitter", "submitter123", "submitter")]


def seed() -> None:
    with db.tx() as conn:
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            for u, pw, role in DEMO_USERS:
                conn.execute("INSERT INTO users VALUES (?,?,?)", (u, auth.hash_password(pw), role))
        if conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0] == 0:
            for r in json.load(open(config.BASE_DIR / "data" / "seed_requests.json")):
                conn.execute("INSERT INTO requests (unit, description, created_by, created_at) VALUES (?,?,?,?)",
                             (r["unit"], r["description"], "seed", db.now()))


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    seed()
    yield


app = FastAPI(title="AI Workflow Assistant", lifespan=lifespan)
router = APIRouter(prefix="/api")


def get_model_factory():
    """Dependency returning mode -> model. Tests override this with a mock."""
    def factory(mode: str):
        return models.DemoModel() if mode == "demo" else models.OpenAIModel()
    return factory


def rows(conn, sql, *params):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


@router.get("/health")
def health():
    return {"ok": True, "llm_configured": bool(config.openai_api_key())}


@router.post("/auth/login")
def login(body: LoginIn):
    with db.tx() as conn:
        row = conn.execute("SELECT * FROM users WHERE username=?", (body.username,)).fetchone()
        if not row or not auth.verify_password(body.password, row["password_hash"]):
            db.audit(conn, body.username[:50], "login_failed")
            raise HTTPException(401, "Invalid credentials")
    return {"token": auth.make_token(row["username"]), "username": row["username"], "role": row["role"],
            "permissions": sorted(auth.ROLE_PERMISSIONS.get(row["role"], set()))}


@router.get("/me")
def me(user: dict = Depends(auth.current_user)):
    return user


@router.post("/requests", status_code=201)
def submit_request(body: RequestIn, user: dict = Depends(auth.require("submit"))):
    with db.tx() as conn:
        cur = conn.execute("INSERT INTO requests (unit, description, created_by, created_at) VALUES (?,?,?,?)",
                           (body.unit, body.description, user["username"], db.now()))
        db.audit(conn, user["username"], "request_submitted", request_id=cur.lastrowid)
        return dict(conn.execute("SELECT * FROM requests WHERE id=?", (cur.lastrowid,)).fetchone())


@router.get("/requests")
def list_requests(user: dict = Depends(auth.current_user)):
    with db.tx() as conn:
        return rows(conn, "SELECT * FROM requests ORDER BY id DESC")


@router.post("/requests/{request_id}/propose", status_code=201)
def propose(request_id: int, mode: str = "llm", user: dict = Depends(auth.require("submit")),
            factory=Depends(get_model_factory)):
    if mode not in ("llm", "demo"):
        raise HTTPException(422, "mode must be 'llm' or 'demo'")
    with db.tx() as conn:
        req = conn.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
        if not req:
            raise HTTPException(404, "Request not found")
        if conn.execute("SELECT 1 FROM proposals WHERE request_id=? AND status IN ('pending','approved')",
                        (request_id,)).fetchone():
            raise HTTPException(409, "Request already has a pending or approved proposal")

    def fail(status_code: int, kind: str, message: str):
        with db.tx() as conn:
            conn.execute("UPDATE requests SET status='proposal_failed' WHERE id=?", (request_id,))
            db.audit(conn, user["username"], "proposal_failed", request_id=request_id,
                     detail={"kind": kind, "message": message, "mode": mode})
        log.error("proposal failed request=%s kind=%s", request_id, kind)
        raise HTTPException(status_code, {"kind": kind, "message": message})

    try:
        model = factory(mode)
    except models.ModelUnavailable as e:
        fail(503, "missing_api_key", str(e))
    try:
        draft = run_agent(model, request_id, req["unit"], req["description"])
    except AgentError as e:
        fail(502, e.kind, e.message)

    with db.tx() as conn:
        cur = conn.execute(
            "INSERT INTO proposals (request_id, mode, urgency, category, title, description, reasoning, policy_id, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (request_id, model.mode, draft.urgency, draft.category, draft.title, draft.description,
             draft.reasoning, draft.policy_id, db.now()))
        conn.execute("UPDATE requests SET status='proposed' WHERE id=?", (request_id,))
        db.audit(conn, user["username"], "proposal_created", request_id=request_id, proposal_id=cur.lastrowid,
                 detail={"mode": model.mode, "policy_id": draft.policy_id, "urgency": draft.urgency})
        return dict(conn.execute("SELECT * FROM proposals WHERE id=?", (cur.lastrowid,)).fetchone())


@router.get("/proposals")
def list_proposals(user: dict = Depends(auth.current_user)):
    with db.tx() as conn:
        return rows(conn, "SELECT p.*, r.unit, r.description AS request_text FROM proposals p "
                          "JOIN requests r ON r.id = p.request_id ORDER BY p.id DESC")


@router.post("/proposals/{proposal_id}/approve")
def approve(proposal_id: int, edits: Edits | None = None, user: dict = Depends(auth.require("approve"))):
    """Idempotent: the conditional UPDATE lets exactly one caller win; work_orders.proposal_id is UNIQUE."""
    changes = edits.model_dump(exclude_none=True) if edits else {}
    with db.tx() as conn:
        conn.execute("BEGIN IMMEDIATE")
        p = conn.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
        if not p:
            raise HTTPException(404, "Proposal not found")
        if p["status"] == "approved":  # retry: return the existing order, create nothing
            db.audit(conn, user["username"], "approval_retry_ignored", p["request_id"], proposal_id)
            wo = conn.execute("SELECT * FROM work_orders WHERE proposal_id=?", (proposal_id,)).fetchone()
            return {"work_order": dict(wo), "duplicate": True}
        if p["status"] != "pending":
            raise HTTPException(409, f"Proposal is {p['status']}")
        final = {k: changes.get(k, p[k]) for k in ("urgency", "category", "title", "description")}
        edited = sorted(k for k, v in final.items() if v != p[k])
        cur = conn.execute("UPDATE proposals SET status='approved', decided_by=?, decided_at=?, urgency=?, "
                           "category=?, title=?, description=? WHERE id=? AND status='pending'",
                           (user["username"], db.now(), *final.values(), proposal_id))
        if cur.rowcount != 1:
            raise HTTPException(409, "Proposal already decided")
        try:
            wo_id = conn.execute(
                "INSERT INTO work_orders (proposal_id, request_id, urgency, category, title, description, policy_id,"
                " approved_by, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (proposal_id, p["request_id"], *final.values(), p["policy_id"], user["username"], db.now())).lastrowid
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Work order already exists")
        conn.execute("UPDATE requests SET status='approved' WHERE id=?", (p["request_id"],))
        db.audit(conn, user["username"], "proposal_approved", p["request_id"], proposal_id,
                 {"work_order_id": wo_id, "edited_fields": edited})
        log.info("proposal %s approved by %s -> work order %s", proposal_id, user["username"], wo_id)
        return {"work_order": dict(conn.execute("SELECT * FROM work_orders WHERE id=?", (wo_id,)).fetchone()),
                "duplicate": False}


@router.post("/proposals/{proposal_id}/reject")
def reject(proposal_id: int, body: RejectIn, user: dict = Depends(auth.require("approve"))):
    with db.tx() as conn:
        conn.execute("BEGIN IMMEDIATE")
        p = conn.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
        if not p:
            raise HTTPException(404, "Proposal not found")
        if p["status"] != "pending":
            raise HTTPException(409, f"Proposal is {p['status']}")
        conn.execute("UPDATE proposals SET status='rejected', decided_by=?, decided_at=?, reject_reason=? WHERE id=?",
                     (user["username"], db.now(), body.reason, proposal_id))
        conn.execute("UPDATE requests SET status='rejected' WHERE id=?", (p["request_id"],))
        db.audit(conn, user["username"], "proposal_rejected", p["request_id"], proposal_id, {"reason": body.reason})
        return {"status": "rejected"}


@router.get("/work-orders")
def list_work_orders(user: dict = Depends(auth.current_user)):
    with db.tx() as conn:
        return rows(conn, "SELECT * FROM work_orders ORDER BY id DESC")


@router.get("/audit")
def audit_log(user: dict = Depends(auth.current_user)):
    with db.tx() as conn:
        return rows(conn, "SELECT * FROM audit_log ORDER BY id DESC LIMIT 200")


app.include_router(router)
