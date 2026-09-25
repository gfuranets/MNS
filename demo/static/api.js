/* api.js - shared helpers. Loaded before script.js.
   The demo has no accounts: the page always acts as the demo user. */

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
     raw  - return the Response itself (file downloads) */
async function api(path, { method = "GET", body, form, raw = false } = {}) {
  const headers = {};

  let payload;
  if (form) {
    payload = form;   // the browser sets the multipart boundary itself
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  const res = await fetch(path, { method, headers, body: payload });

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
