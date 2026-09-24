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
      .map((e) => `${(e.loc || []).slice(1).join(".")}: ${e.msg.replace(/^Value error, /, "")}`)
      .join("; ");
  }
  return `Request failed (${status})`;
}

/* One wrapper for every API call.
     body - sent as JSON
     form - a FormData, sent as multipart (file uploads)
     raw  - return the Response itself (file downloads)
   A 401 on a logged-in request means the token expired: back to login. */
async function api(path, { method = "GET", body, form, raw = false } = {}) {
  const headers = {};
  const saved = token.get();
  if (saved) headers.Authorization = `Bearer ${saved}`;

  let payload;
  if (form) {
    payload = form;   // the browser sets the multipart boundary itself
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  const res = await fetch(path, { method, headers, body: payload });

  if (res.status === 401 && saved) {
    logOut();
    throw new Error("Your session expired. Log in again.");
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(readError(data.detail, res.status));
  }
  if (raw) return res;
  if (res.status === 204) return null;
  return res.json();
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
