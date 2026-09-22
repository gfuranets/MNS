/* auth.js - shared helpers. Loaded by every page, before that page's own script.
   The JWT lives in localStorage and is attached to each request as
   `Authorization: Bearer <token>`. */

const TOKEN_KEY = "mns_token";

const token = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (value) => localStorage.setItem(TOKEN_KEY, value),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

/* FastAPI returns validation errors as a list of objects, and our own errors
   as a plain string. Turn either into one readable line. */
function readError(detail, status) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((e) => `${(e.loc || []).slice(1).join(".")}: ${e.msg}`)
      .join("; ");
  }
  return `Request failed (${status})`;
}

async function api(path, { method = "GET", body } = {}) {
  const headers = { "Content-Type": "application/json" };
  const saved = token.get();
  if (saved) headers.Authorization = `Bearer ${saved}`;

  const res = await fetch(path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(readError(data.detail, res.status));
  return data;
}

function showMessage(el, text, kind = "error") {
  el.textContent = text;
  el.className = `message ${kind}`;
}

/* Send anyone without a token to the login page. */
function requireLogin() {
  if (!token.get()) {
    window.location.replace("login.html");
    return false;
  }
  return true;
}

function logOut() {
  token.clear();
  window.location.replace("login.html");
}
