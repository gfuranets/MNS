"""main.py - DEMO build of the FastAPI app: same frontend, no database.

Every GET answers from a JSON snapshot in data/<language>.json (taken from the
real app for the demo persona "User Demo"). Writes are accepted and answered
with plausible data; a few (settings, profile, tasks, log, inbox) are kept in
memory so the UI reacts during the demo. Restarting the server resets it all.

Run:  uvicorn main:app --reload   (from inside demo/)
There is no login: the app always opens as the demo user.
"""
import copy
import itertools
import json
from datetime import date, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

HERE = Path(__file__).parent
SNAPSHOTS = {lang: json.loads((HERE / "data" / f"{lang}.json").read_text(encoding="utf-8"))
             for lang in ("en", "lv")}

app = FastAPI(title="MNS - Medical Notification System (demo)")


# --------------------------------------------------------------------------
# in-memory state
# --------------------------------------------------------------------------

class State:
    """Everything the demo remembers between requests."""

    def __init__(self):
        self.me = copy.deepcopy(SNAPSHOTS["en"]["/api/me"])
        self.added_tasks: list[dict] = []
        self.added_log: list[dict] = []
        self.deleted_tasks: set[int] = set()
        self.deleted_log: set[int] = set()
        self.accepted: set[int] = set()
        self.ids = itertools.count(10_000)

    @property
    def lang(self) -> str:
        return self.me.get("language", "en")

    def snap(self, key: str):
        """A deep copy of the snapshot answer for `key` in the current language."""
        data = SNAPSHOTS[self.lang].get(key)
        if data is None:
            data = SNAPSHOTS["en"].get(key)
        return copy.deepcopy(data)


state = State()


def now() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def log_entry(title: str, category: str, done_on: str, **extra) -> dict:
    entry = {
        "id": next(state.ids), "title": title, "category": category, "done_on": done_on,
        "renew_on": None, "checkup_type_id": None, "task_id": None, "notes": None,
        "attachment_name": None, "created_at": now(),
    }
    entry.update(extra)
    return entry


def found(data):
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return data


# --------------------------------------------------------------------------
# user system
# --------------------------------------------------------------------------

@app.get("/api/me")
def me():
    return state.me


@app.post("/api/me/consent")
def consent():
    state.me["consent_at"] = state.me.get("consent_at") or now()
    return state.me


@app.put("/api/me/profile")
async def set_profile(request: Request):
    data = await request.json()
    state.me.update({k: v for k, v in data.items() if k in state.me})
    state.me["risk_factors"] = [
        {"code": r["code"], "scope": r["scope"], "note": r.get("note")}
        for r in data.get("risk_factors", [])
    ]
    return state.me


@app.patch("/api/me/settings")
async def set_settings(request: Request):
    data = await request.json()
    state.me.update({k: v for k, v in data.items() if k in state.me and v is not None})
    return state.me


@app.get("/api/me/export")
def export_my_data():
    return JSONResponse(state.snap("/api/me/export") | {"profile": state.me})


@app.delete("/api/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me():
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------
# home, schedule, calendar, checkups
# --------------------------------------------------------------------------

@app.get("/api/home")
def home():
    data = state.snap("/api/home")
    data["name"] = state.me["name"]
    return data


@app.get("/api/schedule")
def schedule(source: str = "all"):
    if source not in ("all", "recommended", "mine"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "source must be all, recommended or mine")
    return [i for i in state.snap(f"/api/schedule?source={source}")
            if i.get("task_id") not in state.deleted_tasks]


@app.get("/api/calendar")
def calendar(month: str):
    return state.snap(f"/api/calendar?month={month}") or []


@app.get("/api/checkups")
def checkups():
    return state.snap("/api/checkups")


@app.get("/api/checkups/{checkup_id}")
def checkup(checkup_id: int):
    return found(state.snap(f"/api/checkups/{checkup_id}"))


@app.post("/api/checkups/{checkup_id}/done")
async def checkup_done(checkup_id: int, request: Request):
    data = await request.json()
    detail = state.snap(f"/api/checkups/{checkup_id}") or {}
    entry = log_entry(detail.get("name", "Check-up"), detail.get("category", "checkup"),
                      data.get("done_on") or date.today().isoformat(),
                      checkup_type_id=checkup_id, notes=data.get("notes"))
    state.added_log.append(entry)
    return {"entry": entry, "next_due": None}


# --------------------------------------------------------------------------
# the user's own tasks
# --------------------------------------------------------------------------

def all_tasks() -> list[dict]:
    return [t for t in (state.snap("/api/tasks") or []) + copy.deepcopy(state.added_tasks)
            if t["id"] not in state.deleted_tasks]


@app.get("/api/tasks")
def tasks():
    return all_tasks()


@app.post("/api/tasks", status_code=status.HTTP_201_CREATED)
async def create_task(request: Request):
    data = await request.json()
    dates = [data["first_date"], *data.get("extra_dates", [])]
    task = {
        "id": next(state.ids), "title": data["title"], "category": data["category"],
        "description": data.get("description"), "doctor_name": data.get("doctor_name"),
        "doctor_specialty": data.get("doctor_specialty"),
        "repeat_every": data.get("repeat_every"), "repeat_unit": data.get("repeat_unit"),
        "remind_every_minutes": data.get("remind_every_minutes"), "created_at": now(),
        "events": [{"id": next(state.ids), "due_on": d, "status": "pending", "done_on": None}
                   for d in sorted(dates)],
    }
    state.added_tasks.append(task)
    return task


@app.get("/api/tasks/{task_id}")
def task(task_id: int):
    return found(next((t for t in all_tasks() if t["id"] == task_id), None))


@app.delete("/api/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int):
    state.deleted_tasks.add(task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/tasks/{task_id}/dates")
async def add_task_date(task_id: int, request: Request):
    data = await request.json()
    t = task(task_id)
    t["events"].append({"id": next(state.ids), "due_on": data["due_on"], "status": "pending", "done_on": None})
    t["events"].sort(key=lambda e: e["due_on"])
    return t


@app.post("/api/task-events/{event_id}/done")
async def event_done(event_id: int, request: Request):
    data = await request.json()
    entry = log_entry("Done", "other", data.get("done_on") or date.today().isoformat(), notes=data.get("notes"))
    return {"entry": entry, "next_due": None}


@app.post("/api/task-events/{event_id}/missed")
def event_missed(event_id: int):
    return {"entry": None, "next_due": None}


# --------------------------------------------------------------------------
# health log, labs, vaccinations
# --------------------------------------------------------------------------

@app.get("/api/categories")
def categories():
    return state.snap("/api/categories")


@app.get("/api/log")
def log(category: str | None = None):
    key = f"/api/log?category={category}" if category else "/api/log"
    lines = state.snap(key) or []
    added = [e for e in state.added_log if not category or e["category"] == category]
    lines = copy.deepcopy(added[::-1]) + lines
    return [l for l in lines if l.get("id") not in state.deleted_log]


@app.get("/api/labs")
def labs():
    return state.snap("/api/labs")


@app.post("/api/log", status_code=status.HTTP_201_CREATED)
async def create_log(request: Request):
    data = await request.json()
    entry = log_entry(data["title"], data["category"], data["done_on"],
                      renew_on=data.get("renew_on"), checkup_type_id=data.get("checkup_type_id"),
                      notes=data.get("notes"))
    state.added_log.append(entry)
    return entry


@app.delete("/api/log/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_log(entry_id: int):
    state.deleted_log.add(entry_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/log/{entry_id}/attachment")
async def upload_attachment(entry_id: int, request: Request):
    form = await request.form()
    upload = form.get("file")
    name = getattr(upload, "filename", None) or "attachment"
    entry = next((e for e in state.added_log if e["id"] == entry_id), None)
    if entry is None:
        entry = log_entry("Result", "other", date.today().isoformat(), id=entry_id)
    entry["attachment_name"] = name
    return entry


@app.get("/api/log/{entry_id}/attachment")
def download_attachment(entry_id: int):
    return PlainTextResponse(
        "This is a demo build - attachments are not stored.",
        headers={"Content-Disposition": 'attachment; filename="demo-attachment.txt"'},
    )


@app.get("/api/vaccinations")
def vaccinations():
    return state.snap("/api/vaccinations")


# --------------------------------------------------------------------------
# procedures and preparation plans
# --------------------------------------------------------------------------

@app.get("/api/procedures")
def procedures(q: str | None = None):
    items = state.snap("/api/procedures")
    if q:
        needle = q.lower()
        items = [p for p in items if needle in json.dumps(p, ensure_ascii=False).lower()]
    return items


@app.get("/api/procedures/{procedure_id}")
def procedure(procedure_id: int):
    return found(state.snap(f"/api/procedures/{procedure_id}"))


@app.post("/api/procedures/{procedure_id}/plans", status_code=status.HTTP_201_CREATED)
async def create_plan(procedure_id: int, request: Request):
    data = await request.json()
    proc = procedure(procedure_id)
    wanted = {r.get("step_id"): r.get("remind_at") for r in data.get("reminders", [])}
    steps = proc.get("steps", [])
    return {
        "id": next(state.ids), "procedure_id": procedure_id, "procedure_name": proc.get("name", ""),
        "appointment_at": data["appointment_at"],
        "items": [
            {"id": next(state.ids), "step_id": s.get("id"), "text": s.get("text", ""),
             "checked": False, "remind_at": wanted.get(s.get("id")), "sent_at": None}
            for s in steps
        ],
    }


@app.get("/api/prep-plans")
def prep_plans():
    return state.snap("/api/prep-plans") or []


@app.patch("/api/prep-items/{item_id}")
async def check_prep_item(item_id: int, request: Request):
    data = await request.json()
    return {"id": item_id, "step_id": 0, "text": "", "checked": bool(data.get("checked")),
            "remind_at": None, "sent_at": None}


@app.delete("/api/prep-plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(plan_id: int):
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------
# notifications
# --------------------------------------------------------------------------

@app.get("/api/notifications")
def notifications():
    inbox = state.snap("/api/notifications")
    for n in inbox.get("items", []):
        if n["id"] in state.accepted and not n.get("accepted_at"):
            n["accepted_at"] = now()
    inbox["waiting"] = sum(1 for n in inbox.get("items", []) if not n.get("accepted_at"))
    return inbox


@app.get("/api/reminders/pending")
def pending():
    return [p for p in state.snap("/api/reminders/pending") or []
            if p.get("notification_id") not in state.accepted]


@app.post("/api/notifications/{notification_id}/accept", status_code=status.HTTP_204_NO_CONTENT)
def accept(notification_id: int):
    state.accepted.add(notification_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/notifications/accept-all", status_code=status.HTTP_204_NO_CONTENT)
def accept_all():
    state.accepted.update(n["id"] for n in state.snap("/api/notifications").get("items", []))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/notifications/check")
def check_now():
    return {"users_checked": 1, "push": 1, "sms": 0, "email": 1 if state.me.get("remind_email") else 0,
            "prep": 0, "dry_run": True, "email_dry_run": True}


@app.get("/api/notifications/recipients")
def recipients():
    return state.snap("/api/notifications/recipients") or {"recipients": 1}


@app.post("/api/notifications/send")
def send():
    return {"dry_run": True, "sent": 0, "skipped": 0, "failed": 0, "results": [
        {"user_id": state.me["id"], "name": f"{state.me['name']} {state.me.get('surname') or ''}".strip(),
         "phone": state.me.get("phone"), "status": "dry_run", "detail": None},
    ]}


# Anything else under /api is not part of the demo.
@app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def not_in_demo(rest: str):
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Not available in the demo")


# The frontend, served from the same origin - mounted last so /api wins.
app.mount("/", StaticFiles(directory=HERE / "static", html=True), name="static")
