import { useCallback, useEffect, useState } from "react";
import { api, hasToken, setToken } from "./api.js";

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
    <form className="card login" onSubmit={submit}>
      <h2>Reviewer login</h2>
      <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="username" />
      <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="password" />
      <button>Log in</button>
      {error && <p className="error">{error}</p>}
      <p className="muted">Demo credentials are in the README.</p>
    </form>
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
      onDone();
    } catch (err) {
      notify(err.message);
    }
  };
  return (
    <form className="card" onSubmit={submit}>
      <h3>Submit maintenance request</h3>
      <input value={unit} onChange={(e) => setUnit(e.target.value)} placeholder="Unit (e.g. A-101)" required />
      <textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Describe the problem" required minLength={5} />
      <button>Submit</button>
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
    <div className="card">
      <h3>Requests</h3>
      <table>
        <thead><tr><th>#</th><th>Unit</th><th>Description</th><th>Status</th><th /></tr></thead>
        <tbody>
          {requests.map((r) => (
            <tr key={r.id}>
              <td>{r.id}</td><td>{r.unit}</td><td>{r.description}</td>
              <td><span className={`tag ${r.status}`}>{r.status}</span></td>
              <td>
                {["submitted", "proposal_failed", "rejected"].includes(r.status) && (
                  <button onClick={() => propose(r.id)}>{demo ? "Draft (demo)" : "Draft with AI"}</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ProposalCard({ p, canApprove, onChange, notify }) {
  const [edit, setEdit] = useState({ urgency: p.urgency, category: p.category, title: p.title, description: p.description });
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
    <div className="card proposal">
      <div className="row">
        <b>Proposal #{p.id} · request #{p.request_id} · unit {p.unit}</b>
        <span className={`tag ${p.mode}`}>{p.mode === "demo" ? "DEMO MODE - not an LLM" : "LLM draft"}</span>
      </div>
      <p className="muted">Request (untrusted text): “{p.request_text}”</p>
      <p><b>Reasoning:</b> {p.reasoning}</p>
      <p><b>Policy reference:</b> {p.policy_id}</p>
      <label>Urgency
        <select value={edit.urgency} onChange={set("urgency")}>
          {["emergency", "urgent", "routine", "low"].map((u) => <option key={u}>{u}</option>)}
        </select>
      </label>
      <label>Category <input value={edit.category} onChange={set("category")} /></label>
      <label>Title <input value={edit.title} onChange={set("title")} /></label>
      <label>Description <textarea value={edit.description} onChange={set("description")} /></label>
      {canApprove ? (
        <div className="row">
          <button onClick={() => act("approve", edit)}>Approve{" "}(with edits above)</button>
          <button className="danger" onClick={() => {
            const reason = window.prompt("Reason for rejection?");
            if (reason) act("reject", { reason });
          }}>Reject</button>
        </div>
      ) : <p className="muted">Your role cannot approve proposals.</p>}
    </div>
  );
}

function Table({ title, rows, cols }) {
  return (
    <div className="card">
      <h3>{title}</h3>
      {rows.length === 0 ? <p className="muted">None yet.</p> : (
        <table>
          <thead><tr>{cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
          <tbody>{rows.map((r) => <tr key={r.id}>{cols.map((c) => <td key={c}>{String(r[c] ?? "")}</td>)}</tr>)}</tbody>
        </table>
      )}
    </div>
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

  if (!user) return <main><h1>AI Workflow Assistant</h1><Login onLogin={setUser} /></main>;
  const pending = data.proposals.filter((p) => p.status === "pending");
  return (
    <main>
      <header className="row">
        <h1>AI Workflow Assistant</h1>
        <span>{user.username} ({user.role}) <button onClick={() => { setToken(null); setUser(null); }}>Log out</button></span>
      </header>
      <p className="muted">Fictional property-management demo. Synthetic data only.</p>
      <label className="card row">
        <input type="checkbox" checked={demo} onChange={(e) => setDemo(e.target.checked)} />
        Demo mode: deterministic keyword rules, no LLM call
        {!demo && health && !health.llm_configured && <b className="error"> · OPENAI_API_KEY not set, AI drafts will fail; use demo mode.</b>}
      </label>
      {message && <p className="error card">{message}</p>}
      <SubmitForm onDone={load} notify={setMessage} />
      <Requests requests={data.requests} demo={demo} onChange={load} notify={setMessage} />
      <h2>Review queue ({pending.length})</h2>
      {pending.length === 0 && <p className="muted">No proposals awaiting review.</p>}
      {pending.map((p) => (
        <ProposalCard key={p.id} p={p} canApprove={user.permissions.includes("approve")} onChange={load} notify={setMessage} />
      ))}
      <Table title="Work orders (created only on human approval)" rows={data.orders}
        cols={["id", "request_id", "urgency", "category", "title", "policy_id", "approved_by", "status"]} />
      <Table title="Audit history" rows={data.audit} cols={["ts", "actor", "action", "request_id", "proposal_id", "detail"]} />
    </main>
  );
}
