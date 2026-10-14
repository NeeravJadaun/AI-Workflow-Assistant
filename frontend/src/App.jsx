import { useCallback, useEffect, useState } from "react";
import { api, hasToken, setToken } from "./api.js";
import { Alert, Check, Flask, Logout, Sparkles, Wrench, X } from "./icons.jsx";

const URGENCIES = ["emergency", "urgent", "routine", "low"];

function Brand() {
  return (
    <div className="brand">
      <span className="brand-mark"><Wrench width={18} height={18} /></span>
      <span>AI Workflow Assistant<small>Maple Court Property Management (fictional demo)</small></span>
    </div>
  );
}

function Badge({ kind, children }) {
  return <span className={`badge ${kind}`}>{children ?? kind}</span>;
}

function ModeBadge({ mode }) {
  return mode === "demo"
    ? <Badge kind="demo"><Flask /> DEMO MODE - not an LLM</Badge>
    : <Badge kind="llm"><Sparkles /> LLM draft</Badge>;
}

function Login({ onLogin }) {
  const [username, setUsername] = useState("reviewer");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const submit = async (e) => {
    e.preventDefault();
    try {
      const u = await api("/auth/login", { method: "POST", body: { username, password } });
      setToken(u.token);
      onLogin(u);
    } catch (err) {
      setError(err.message);
    }
  };
  return (
    <div className="login-wrap">
      <form className="card login" onSubmit={submit}>
        <Brand />
        <h2>Reviewer sign in</h2>
        <label className="field">Username
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
        </label>
        <label className="field">Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
        </label>
        <button className="primary" type="submit">Sign in</button>
        {error && <div className="alert error" role="alert"><Alert /> {error}</div>}
        <div className="hint">Demo accounts are listed in the README (<code>reviewer</code> can approve, <code>submitter</code> cannot).</div>
      </form>
    </div>
  );
}

function SubmitForm({ onDone, notify }) {
  const [unit, setUnit] = useState("");
  const [description, setDescription] = useState("");
  const submit = async (e) => {
    e.preventDefault();
    try {
      await api("/requests", { method: "POST", body: { unit, description } });
      setUnit("");
      setDescription("");
      notify("");
      onDone();
    } catch (err) {
      notify(err.message);
    }
  };
  return (
    <form className="card" onSubmit={submit}>
      <div className="card-head"><h2>New maintenance request</h2></div>
      <div style={{ display: "grid", gap: 10 }}>
        <label className="field">Unit
          <input value={unit} onChange={(e) => setUnit(e.target.value)} placeholder="e.g. A-101" required maxLength={20} />
        </label>
        <label className="field">Problem description
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="e.g. Bathroom tap is leaking" required minLength={5} maxLength={1000} />
        </label>
        <div><button className="primary" type="submit">Submit request</button></div>
      </div>
    </form>
  );
}

function Requests({ requests, demo, onChange, notify }) {
  const propose = async (id) => {
    try {
      await api(`/requests/${id}/propose?mode=${demo ? "demo" : "llm"}`, { method: "POST" });
      notify("");
    } catch (err) {
      notify(`Request #${id}: ${err.message}`);
    }
    onChange();
  };
  return (
    <section className="card">
      <div className="card-head"><h2>Requests<span className="count">{requests.length}</span></h2></div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>#</th><th>Unit</th><th>Description</th><th>Status</th><th><span className="sr-only">Action</span></th></tr></thead>
          <tbody>
            {requests.map((r) => (
              <tr key={r.id}>
                <td>{r.id}</td>
                <td className="nowrap">{r.unit}</td>
                <td>{r.description}</td>
                <td><Badge kind={r.status}>{r.status.replace("_", " ")}</Badge></td>
                <td className="nowrap">
                  {["submitted", "proposal_failed", "rejected"].includes(r.status) && (
                    <button className="small" onClick={() => propose(r.id)}>
                      {demo ? <Flask /> : <Sparkles />}{demo ? "Draft (demo)" : "Draft with AI"}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ProposalCard({ p, canApprove, onChange, notify }) {
  const [edit, setEdit] = useState({ urgency: p.urgency, category: p.category, title: p.title, description: p.description });
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const act = async (path, body) => {
    try {
      await api(`/proposals/${p.id}/${path}`, { method: "POST", body });
      notify("");
    } catch (err) {
      notify(err.message);
    }
    onChange();
  };
  const set = (k) => (e) => setEdit({ ...edit, [k]: e.target.value });
  return (
    <article className="card proposal">
      <div className="proposal-head">
        <h3>Proposal #{p.id} · request #{p.request_id} · unit {p.unit}</h3>
        <ModeBadge mode={p.mode} />
      </div>
      <div className="quote"><span className="muted">Tenant request (untrusted text)</span>{p.request_text}</div>
      <p className="reasoning"><b>Agent reasoning:</b> {p.reasoning}</p>
      <p className="reasoning"><b>Policy reference:</b> <Badge kind="routine">{p.policy_id}</Badge></p>
      <div className="grid2">
        <label className="field">Urgency
          <select value={edit.urgency} onChange={set("urgency")}>{URGENCIES.map((u) => <option key={u}>{u}</option>)}</select>
        </label>
        <label className="field">Category <input value={edit.category} onChange={set("category")} /></label>
      </div>
      <label className="field">Work order title <input value={edit.title} onChange={set("title")} /></label>
      <label className="field">Work order description <textarea value={edit.description} onChange={set("description")} /></label>
      {canApprove ? (
        rejecting ? (
          <div className="reject-box">
            <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason for rejection" aria-label="Reason for rejection" autoFocus />
            <button className="danger" disabled={!reason.trim()} onClick={() => act("reject", { reason: reason.trim() })}><X /> Confirm reject</button>
            <button onClick={() => setRejecting(false)}>Cancel</button>
          </div>
        ) : (
          <div className="actions">
            <button className="approve" onClick={() => act("approve", edit)}><Check /> Approve and create work order</button>
            <button className="danger" onClick={() => setRejecting(true)}><X /> Reject</button>
          </div>
        )
      ) : <div className="alert warn"><Alert /> Your role cannot approve proposals.</div>}
    </article>
  );
}

function DataTable({ title, rows, cols, render = {} }) {
  return (
    <section className="card full">
      <div className="card-head"><h2>{title}<span className="count">{rows.length}</span></h2></div>
      {rows.length === 0 ? <p className="empty">None yet.</p> : (
        <div className="table-wrap">
          <table>
            <thead><tr>{cols.map((c) => <th key={c}>{c.replace("_", " ")}</th>)}</tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.id}>{cols.map((c) => <td key={c} className={c === "ts" ? "nowrap" : ""}>{render[c] ? render[c](r[c]) : String(r[c] ?? "")}</td>)}</tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export default function App() {
  const [user, setUser] = useState(null);
  const [data, setData] = useState({ requests: [], proposals: [], orders: [], audit: [] });
  const [demo, setDemo] = useState(false);
  const [health, setHealth] = useState(null);
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    try {
      const [requests, proposals, orders, audit] = await Promise.all(
        ["/requests", "/proposals", "/work-orders", "/audit"].map((p) => api(p)));
      setData({ requests, proposals, orders, audit });
    } catch (err) {
      if (err.status === 401) { setToken(null); setUser(null); } else setMessage(err.message);
    }
  }, []);

  useEffect(() => { api("/health").then(setHealth).catch(() => {}); }, []);
  useEffect(() => {
    if (hasToken() && !user) api("/me").then(setUser).catch(() => setToken(null));
  }, [user]);
  useEffect(() => { if (user) load(); }, [user, load]);

  if (!user) return <Login onLogin={setUser} />;

  const pending = data.proposals.filter((p) => p.status === "pending");
  const awaiting = data.requests.filter((r) => ["submitted", "proposal_failed", "rejected"].includes(r.status)).length;
  const noKey = health && !health.llm_configured;
  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <Brand />
          <div className="user">
            <span>{user.username}</span><span className="role">{user.role}</span>
            <button className="small" onClick={() => { setToken(null); setUser(null); }}><Logout /> Log out</button>
          </div>
        </div>
      </header>
      <main>
        <div className="intro">
          <ol className="steps" aria-label="Workflow">
            <li>Request submitted</li><li>Agent drafts proposal</li><li className="human">Human approves, edits or rejects</li><li>Work order created</li>
          </ol>
        </div>
        <div className="card mode">
          <label className="switch">
            <input type="checkbox" checked={demo} onChange={(e) => setDemo(e.target.checked)} />
            Demo mode
          </label>
          <span className="muted">Deterministic keyword rules, no LLM call. Drafts are labeled as demo.</span>
          {!demo && noKey && <span className="badge rejected"><Alert /> OPENAI_API_KEY not set: AI drafts will fail, use demo mode</span>}
        </div>
        {message && <div className="alert error" role="alert"><Alert /> {message}</div>}
        <div className="stats">
          <div className="card stat"><b>{awaiting}</b><span>Requests awaiting a draft</span></div>
          <div className="card stat"><b>{pending.length}</b><span>Proposals awaiting review</span></div>
          <div className="card stat"><b>{data.orders.length}</b><span>Work orders created</span></div>
        </div>
        <div className="layout">
          <div className="stack">
            <SubmitForm onDone={load} notify={setMessage} />
            <Requests requests={data.requests} demo={demo} onChange={load} notify={setMessage} />
          </div>
          <div>
            <h2 style={{ marginBottom: 12 }}>Review queue<span className="count">{pending.length}</span></h2>
            {pending.length === 0 && <div className="card empty">No proposals awaiting review. Draft a request to start.</div>}
            {pending.map((p) => (
              <ProposalCard key={p.id} p={p} canApprove={user.permissions.includes("approve")} onChange={load} notify={setMessage} />
            ))}
          </div>
        </div>
        <DataTable title="Work orders (created only on human approval)" rows={data.orders}
          cols={["id", "request_id", "urgency", "category", "title", "policy_id", "approved_by", "status"]}
          render={{ urgency: (v) => <Badge kind={v}>{v}</Badge>, status: (v) => <Badge kind="approved">{v}</Badge> }} />
        <DataTable title="Audit history" rows={data.audit} cols={["ts", "actor", "action", "request_id", "proposal_id", "detail"]}
          render={{ detail: (v) => <code>{v ?? ""}</code>, ts: (v) => v.replace("T", " ").replace("+00:00", " UTC") }} />
      </main>
    </>
  );
}
