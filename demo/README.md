# Demo build

A copy of the app's frontend (`static/`, `templates/`) with a stand-in FastAPI
server (`main.py`) — no database, no auth, no emails/SMS.

- Every screen reads from `data/en.json` / `data/lv.json`, a snapshot of the
  real API for the persona **User Demo** (male, born 1991-04-18, Latvia).
- Any email + password logs in (the login form is prefilled).
- Adding/deleting tasks and log entries, settings, profile edits and the inbox
  work in memory only; restarting the server resets everything.
- Attachments are not stored — downloading one returns a placeholder file.

```bash
cd demo
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```
