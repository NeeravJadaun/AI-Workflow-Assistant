let token = sessionStorage.getItem("token");

export const setToken = (t) => {
  token = t;
  t ? sessionStorage.setItem("token", t) : sessionStorage.removeItem("token");
};
export const hasToken = () => !!token;

export async function api(path, { method = "GET", body } = {}) {
  const res = await fetch("/api" + path, {
    method,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = data.detail;
    const msg = typeof d === "string" ? d : d?.message || (Array.isArray(d) ? d.map((x) => x.msg).join("; ") : res.statusText);
    const err = new Error(msg);
    err.status = res.status;
    throw err;
  }
  return data;
}
