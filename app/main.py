"""main.py - the FastAPI app: API routes plus the static frontend.

Routes stay thin. They validate input (Pydantic does that automatically),
call crud/auth/planner, and return a schema. No SQL lives in this file.
"""
import calendar
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

import auth
import crud
import notifications
import planner
import reminders
from database import get_db
from models import LAB_CATEGORIES, LogEntry, Notification, PrepPlan, User, localized
from schema import (
    CalendarEntry,
    CatalogCheck,
    CheckupDetail,
    Counts,
    DoneOut,
    HomeOut,
    Inbox,
    ItemChecked,
    ItemOut,
    LabPoint,
    LabSeries,
    LogEntryCreate,
    LogEntryOut,
    LogLine,
    MarkDone,
    NotificationCreate,
    NotificationItem,
    NotificationOut,
    PopupOut,
    PrepPlanCreate,
    PrepPlanItemOut,
    PrepPlanOut,
    ProcedureDetail,
    ProcedureListItem,
    ProcedureStepOut,
    ProfileUpdate,
    RecipientCount,
    RecipientResult,
    ReminderRunOut,
    SettingsUpdate,
    TaskCreate,
    TaskDateAdd,
    TaskOut,
    Token,
    UserCreate,
    UserLogin,
    UserOut,
    VaccinationOut,
)

logging.basicConfig(level=logging.INFO)

UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
}
UPLOAD_MAX_BYTES = 10 * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the reminder loop with the server, stop it with the server."""
    UPLOAD_DIR.mkdir(exist_ok=True)
    task = reminders.start()
    yield
    if task:
        task.cancel()


app = FastAPI(title="MNS - Medical Notification System", lifespan=lifespan)

# Only matters if you open the frontend from a *different* origin, e.g. VS Code
# Live Server on :5500. When FastAPI serves the frontend (the mount at the
# bottom of this file) everything is same-origin and CORS is not involved.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5500", "http://127.0.0.1:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------
# shaping helpers
# --------------------------------------------------------------------------

def item_out(item: planner.Item) -> ItemOut:
    return ItemOut(
        kind=item.kind, id=item.id, task_id=item.task_id, name=item.name,
        category=item.category, coverage=item.coverage, status=item.status,
        due_on=item.due_on, days=item.days, last_done=item.last_done,
        interval_months=item.interval_months,
    )


def plan_out(plan: PrepPlan, language: str) -> PrepPlanOut:
    items = sorted(plan.items, key=lambda i: i.step.position)
    return PrepPlanOut(
        id=plan.id, procedure_id=plan.procedure_id,
        procedure_name=localized(plan.procedure, "name", language),
        appointment_at=plan.appointment_at,
        items=[
            PrepPlanItemOut(
                id=i.id, step_id=i.step_id, text=localized(i.step, "text", language),
                checked=i.checked, remind_at=i.remind_at, sent_at=i.sent_at,
            )
            for i in items
        ],
    )


def popup_out(db: Session, n: Notification) -> PopupOut:
    """A waiting reminder, plus the ids the frontend needs for "Mark as done"."""
    task_id = plan_id = procedure_id = None
    if n.task_event_id is not None:
        event = crud.get_event(db, n.user_id, n.task_event_id)
        task_id = event.task_id if event else None
    if n.prep_item_id is not None:
        item = crud.get_plan_item(db, n.user_id, n.prep_item_id)
        if item:
            plan_id, procedure_id = item.plan_id, item.plan.procedure_id
    return PopupOut(
        notification_id=n.id, kind=n.kind, message=n.message, created_at=n.created_at,
        checkup_type_id=n.checkup_type_id, task_event_id=n.task_event_id,
        task_id=task_id, prep_item_id=n.prep_item_id, prep_plan_id=plan_id, procedure_id=procedure_id,
    )


def find_item(db: Session, user: User, checkup_id: int) -> planner.Item:
    """The schedule entry for one checkup, or 404 if it does not apply to this user."""
    for item in crud.all_items(db, user, date.today()):
        if item.kind == "guideline" and item.id == checkup_id:
            return item
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Not on your schedule")


# --------------------------------------------------------------------------
# user system
# --------------------------------------------------------------------------

@app.post("/api/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(data: UserCreate, db: Session = Depends(get_db)):
    """Onboarding step 1. Returns the new user (never the password hash)."""
    if crud.get_user_by_email(db, data.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    return crud.create_user(db, data)


@app.post("/api/login", response_model=Token)
def login(data: UserLogin, db: Session = Depends(get_db)):
    """Exchange email + password for a JWT."""
    user = crud.get_user_by_email(db, data.email)

    # Deliberately the same error for "no such email" and "wrong password".
    # Different messages would let someone discover which emails are registered.
    if user is None or not auth.verify_password(data.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")

    return Token(access_token=auth.create_access_token(user.id))


@app.get("/api/me", response_model=UserOut)
def me(user: User = Depends(auth.get_current_user)):
    """The logged-in user. `profile_complete: false` = onboarding is not finished."""
    return user


@app.post("/api/me/consent", response_model=UserOut)
def consent(
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Onboarding step 2: the user read the plain-language data notice and agreed."""
    return crud.give_consent(db, user)


@app.put("/api/me/profile", response_model=UserOut)
def set_profile(
    data: ProfileUpdate,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Onboarding step 3, and Profile > Edit: personal data and risk factors."""
    return crud.update_profile(db, user, data)


@app.patch("/api/me/settings", response_model=UserOut)
def set_settings(
    data: SettingsUpdate,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Language, reminders on/off, how early to start, channels, phone."""
    # A phone sent in this request (even an empty one) replaces the saved one.
    phone = data.phone if "phone" in data.model_fields_set else user.phone
    sms_on = data.remind_sms if data.remind_sms is not None else user.remind_sms
    if sms_on and not (phone or "").strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Add a phone number before turning on SMS reminders",
        )
    return crud.update_settings(db, user, data)


@app.get("/api/me/export")
def export_my_data(
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Privacy: everything we hold about you, as one JSON download."""
    return {
        "profile": UserOut.model_validate(user).model_dump(mode="json"),
        "log": [LogEntryOut.model_validate(e).model_dump(mode="json")
                for e in crud.list_log(db, user.id)],
        "tasks": [TaskOut.model_validate(t).model_dump(mode="json")
                  for t in crud.list_tasks(db, user.id)],
        "preparation_plans": [plan_out(p, user.language).model_dump(mode="json")
                              for p in crud.user_plans(db, user.id, upcoming_only=False)],
        "notifications": [
            {"channel": n.channel, "kind": n.kind, "message": n.message,
             "status": n.status, "created_at": n.created_at.isoformat()}
            for n in crud.inbox(db, user.id, limit=10_000)
        ],
    }


@app.delete("/api/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Privacy: delete the account and everything in it, uploaded files included."""
    for name in crud.delete_user(db, user):
        (UPLOAD_DIR / name).unlink(missing_ok=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------
# home, schedule, calendar
# --------------------------------------------------------------------------

@app.get("/api/home", response_model=HomeOut)
def home(
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """The home screen in one call: the pop-up, the status strip, what is coming up."""
    items = crud.all_items(db, user, date.today())
    by_status = {s: [i for i in items if i.status == s] for s in planner.STATUS_ORDER}
    popups = crud.pending_popups(db, user.id)

    return HomeOut(
        name=user.name,
        counts=Counts(**{s: len(v) for s, v in by_status.items()}),
        popup=popup_out(db, popups[0]) if popups else None,
        next_item=item_out(items[0]) if items and items[0].status != "up_to_date" else None,
        coming_up=[item_out(i) for i in items if i.status != "up_to_date"][:8],
        plans=[plan_out(p, user.language) for p in crud.user_plans(db, user.id)],
        pending_reminders=len(popups),
    )


@app.get("/api/schedule", response_model=list[ItemOut])
def schedule(
    source: str = "all",
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Everything on your schedule, most urgent first.

    source = all | recommended (guidelines) | mine (your own tasks)
    """
    kinds = {"all": ("guideline", "task"), "recommended": ("guideline",), "mine": ("task",)}
    if source not in kinds:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "source must be all, recommended or mine")
    return [item_out(i) for i in crud.all_items(db, user, date.today()) if i.kind in kinds[source]]


@app.get("/api/calendar", response_model=list[CalendarEntry])
def month_calendar(
    month: str,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Every dated thing in one month (month = YYYY-MM), for the calendar:
    what is due, what was done, what was missed, and procedure appointments."""
    try:
        first = datetime.strptime(month, "%Y-%m").date()
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "month must look like 2026-09")
    last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
    inside = lambda d: first <= d <= last  # noqa: E731

    entries = [
        CalendarEntry(
            date=i.due_on, kind=i.kind, id=i.task_id if i.kind == "task" else i.id,
            title=i.name, category=i.category, status=i.status,
        )
        for i in crud.all_items(db, user, date.today()) if inside(i.due_on)
    ]
    entries += [
        CalendarEntry(date=e.due_on, kind="task", id=e.task_id, title=e.task.title,
                      category=e.task.category, status="missed")
        for e in crud.missed_events(db, user.id) if inside(e.due_on)
    ]
    entries += [
        CalendarEntry(date=e.done_on, kind="log", id=e.id,
                      title=localized(e.checkup_type, "name", user.language) if e.checkup_type else e.title,
                      category=e.category, status="done")
        for e in crud.list_log(db, user.id) if inside(e.done_on)
    ]
    entries += [
        CalendarEntry(date=p.appointment_at.date(), kind="prep", id=p.procedure_id,
                      title=localized(p.procedure, "name", user.language),
                      category="procedure", status="planned")
        for p in crud.user_plans(db, user.id, upcoming_only=False) if inside(p.appointment_at.date())
    ]
    return sorted(entries, key=lambda e: e.date)


# --------------------------------------------------------------------------
# recommended checks
# --------------------------------------------------------------------------

@app.get("/api/checkups", response_model=list[CatalogCheck])
def checkup_catalog(
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Every state-paid check in the catalog, the ones on your schedule first."""
    today = date.today()
    checks = [
        CatalogCheck(
            id=c.id, name=localized(c, "name", user.language), category=c.category,
            summary=localized(c, "summary", user.language), interval_months=c.interval_months,
            min_age=c.min_age, max_age=c.max_age, sex=c.sex, source_url=c.source_url,
            applies=planner.interval_for(c, user, user.risk_codes, today) is not None,
        )
        for c in crud.all_checkups(db)
    ]
    return sorted(checks, key=lambda c: not c.applies)


@app.get("/api/checkups/{checkup_id}", response_model=CheckupDetail)
def checkup_detail(
    checkup_id: int,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Item detail: the guideline, its source, more info, the prep guide and your history."""
    item = find_item(db, user, checkup_id)
    c = item.source
    return CheckupDetail(
        item=item_out(item),
        summary=localized(c, "summary", user.language),
        more_info=c.more_info, preparation=c.preparation, source_url=c.source_url,
        procedure_id=crud.procedure_ids_by_code(db).get(c.procedure_code) if c.procedure_code else None,
        history=crud.list_log(db, user.id, checkup_id),
    )


@app.post("/api/checkups/{checkup_id}/done", response_model=DoneOut,
          status_code=status.HTTP_201_CREATED)
def mark_checkup_done(
    checkup_id: int,
    data: MarkDone,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """"Mark as done": logs it (today unless a date is given) and clears its reminders."""
    checkup = crud.get_checkup(db, checkup_id)
    if checkup is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such checkup")
    entry = crud.create_log_entry(db, user, LogEntryCreate(
        title=localized(checkup, "name", user.language), category=checkup.category,
        done_on=data.done_on or date.today(), notes=data.notes,
    ), checkup)
    return DoneOut(entry=entry)


# --------------------------------------------------------------------------
# the user's own tasks (Add screen)
# --------------------------------------------------------------------------

@app.get("/api/tasks", response_model=list[TaskOut])
def list_tasks(
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    return crud.list_tasks(db, user.id)


@app.post("/api/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    data: TaskCreate,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Add an appointment, vaccine shot, test... repeating or on manual dates."""
    return crud.create_task(db, user, data)


def _task_or_404(db: Session, user: User, task_id: int):
    task = crud.get_task(db, user.id, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such task")
    return task


@app.get("/api/tasks/{task_id}", response_model=TaskOut)
def get_task(
    task_id: int,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    return _task_or_404(db, user, task_id)


@app.delete("/api/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Removes the task and its future dates. Log entries it produced stay."""
    crud.delete_task(db, _task_or_404(db, user, task_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/tasks/{task_id}/dates", response_model=TaskOut)
def add_task_date(
    task_id: int,
    data: TaskDateAdd,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Manual dates: add another one."""
    task = _task_or_404(db, user, task_id)
    crud.add_task_date(db, task, data.due_on)
    db.refresh(task)
    return task


def _pending_event_or_404(db: Session, user: User, event_id: int):
    event = crud.get_event(db, user.id, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such date")
    if event.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Already marked {event.status}")
    return event


@app.post("/api/task-events/{event_id}/done", response_model=DoneOut)
def task_event_done(
    event_id: int,
    data: MarkDone,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Mark one occurrence done. A repeating task gets its next date."""
    entry, next_due = crud.finish_event(
        db, _pending_event_or_404(db, user, event_id), "done", data.done_on, data.notes
    )
    return DoneOut(entry=entry, next_due=next_due)


@app.post("/api/task-events/{event_id}/missed", response_model=DoneOut)
def task_event_missed(
    event_id: int,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Mark one occurrence missed. A repeating task still gets its next date."""
    _, next_due = crud.finish_event(db, _pending_event_or_404(db, user, event_id), "missed")
    return DoneOut(entry=None, next_due=next_due)


# --------------------------------------------------------------------------
# log
# --------------------------------------------------------------------------

@app.get("/api/categories", response_model=list[str])
def list_categories(
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Every category you have something in - for the Log dropdown."""
    return crud.categories(db, user, crud.all_items(db, user, date.today()))


@app.get("/api/log", response_model=list[LogLine])
def list_log(
    category: str | None = None,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """What you did (done) and what you missed, newest first, optionally one category."""
    reports = crud.lab_reports_by_log_entry(db, user.id)
    lines = [
        LogLine(
            kind="done", id=e.id,
            title=localized(e.checkup_type, "name", user.language) if e.checkup_type else e.title,
            category=e.category, date=e.done_on, notes=e.notes,
            attachment_name=e.attachment_name, checkup_type_id=e.checkup_type_id, task_id=e.task_id,
            lab_report_id=reports.get(e.id),
        )
        for e in crud.list_log(db, user.id)
    ] + [
        LogLine(kind="missed", id=e.id, title=e.task.title, category=e.task.category,
                date=e.due_on, task_id=e.task_id)
        for e in crud.missed_events(db, user.id)
    ]
    if category:
        lines = [line for line in lines if line.category == category]
    return sorted(lines, key=lambda line: (line.date, line.id), reverse=True)


# --------------------------------------------------------------------------
# lab results
# --------------------------------------------------------------------------

@app.get("/api/labs", response_model=list[LabSeries])
def lab_series(
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Your blood test values, one series per test, in catalog category order."""
    series: dict[int, LabSeries] = {}
    for r in crud.lab_results(db, user.id):
        test = r.lab_test
        if test.id not in series:
            series[test.id] = LabSeries(
                code=test.code, name=localized(test, "name", user.language), category=test.category,
                unit=test.unit, summary=localized(test, "summary", user.language), points=[],
            )
        low = float(r.ref_low) if r.ref_low is not None else None
        high = float(r.ref_high) if r.ref_high is not None else None
        series[test.id].points.append(LabPoint(
            report_id=r.report_id, taken_at=r.report.taken_at, value=float(r.value),
            comparator=r.comparator, ref_low=low, ref_high=high,
            flag=planner.lab_flag(float(r.value), r.comparator, low, high),
        ))
    order = {c: i for i, c in enumerate(LAB_CATEGORIES)}
    return sorted(series.values(), key=lambda s: (order[s.category], s.name))


@app.post("/api/log", response_model=LogEntryOut, status_code=status.HTTP_201_CREATED)
def create_log(
    data: LogEntryCreate,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """"Add your own": something you did that is not one of your reminders -
    an extra visit, a test, a vaccine. done_on may be in the past."""
    if data.checkup_type_id is not None:
        checkup = crud.get_checkup(db, data.checkup_type_id)
        if checkup is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such checkup")
    else:
        checkup = crud.find_checkup_by_title(db, data.title)
    return crud.create_log_entry(db, user, data, checkup)


@app.delete("/api/log/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_log(
    entry_id: int,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    entry = crud.get_log_entry(db, user.id, entry_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such entry")
    if entry.attachment_path:
        (UPLOAD_DIR / entry.attachment_path).unlink(missing_ok=True)
    crud.delete_log_entry(db, entry)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/log/{entry_id}/attachment", response_model=LogEntryOut)
async def upload_attachment(
    entry_id: int,
    file: UploadFile = File(...),
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Photo or PDF of a result - multipart upload, one per entry (a new one replaces it)."""
    entry = crud.get_log_entry(db, user.id, entry_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such entry")

    ext = UPLOAD_TYPES.get(file.content_type or "")
    if ext is None:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only PDF and image files are accepted"
        )

    data = await file.read(UPLOAD_MAX_BYTES + 1)
    if len(data) > UPLOAD_MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File is larger than 10 MB")

    # A random name on disk: the user's file name never touches the filesystem path.
    stored = f"{uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR / stored).write_bytes(data)
    if entry.attachment_path:
        (UPLOAD_DIR / entry.attachment_path).unlink(missing_ok=True)

    return crud.set_attachment(db, entry, (file.filename or "attachment")[:255], stored)


@app.get("/api/log/{entry_id}/attachment")
def download_attachment(
    entry_id: int,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    entry = crud.get_log_entry(db, user.id, entry_id)
    if entry is None or not entry.attachment_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No attachment")
    return FileResponse(UPLOAD_DIR / entry.attachment_path, filename=entry.attachment_name)


@app.get("/api/vaccinations", response_model=list[VaccinationOut])
def vaccination_passport(
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """The vaccination passport: each vaccine, when it was given, when to renew.

    Renewal comes from the date entered when logging it, else from the
    recommended interval, else from the task's repeat rule. Recommended
    vaccines you have not logged yet are listed too, with no doses.
    """
    today = date.today()
    items = crud.all_items(db, user, today)
    intervals = {i.id: i.interval_months for i in items if i.kind == "guideline"}

    groups: dict[tuple, list[LogEntry]] = {}
    for e in crud.list_log(db, user.id):      # newest first
        if e.category != "vaccination":
            continue
        key = ("c", e.checkup_type_id) if e.checkup_type_id else \
              ("t", e.task_id) if e.task_id else ("n", e.title.casefold())
        groups.setdefault(key, []).append(e)

    rows = []
    for (source, _), entries in groups.items():
        latest = entries[0]
        renew_on = latest.renew_on
        if renew_on is None and source == "c" and intervals.get(latest.checkup_type_id):
            renew_on = planner.add_months(latest.done_on, intervals[latest.checkup_type_id])
        if renew_on is None and source == "t" and latest.task:
            if latest.task.repeats:
                renew_on = planner.add_interval(latest.done_on, latest.task.repeat_every, latest.task.repeat_unit)
            else:   # manual dates: the next one planned is the renewal
                renew_on = min((e.due_on for e in latest.task.events if e.status == "pending"), default=None)
        rows.append(VaccinationOut(
            name=localized(latest.checkup_type, "name", user.language) if latest.checkup_type else latest.title,
            doses=[e.done_on for e in entries], last_done=latest.done_on, renew_on=renew_on,
            status=planner.status_for(renew_on, today) if renew_on else None,
            checkup_type_id=latest.checkup_type_id,
        ))

    logged = {r.checkup_type_id for r in rows}
    rows += [
        VaccinationOut(name=i.name, doses=[], last_done=None, renew_on=None, status=None,
                       checkup_type_id=i.id)
        for i in items
        if i.kind == "guideline" and i.category == "vaccination" and i.id not in logged
    ]
    return rows


# --------------------------------------------------------------------------
# procedure preparation library (Info)
# --------------------------------------------------------------------------

@app.get("/api/procedures", response_model=list[ProcedureListItem])
def procedures(
    q: str = "",
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Search the preparation library, in English or Latvian ("gastro", "asins")."""
    return [
        ProcedureListItem(id=p.id, code=p.code, name=localized(p, "name", user.language),
                          summary=localized(p, "summary", user.language))
        for p in crud.search_procedures(db, q)
    ]


@app.get("/api/procedures/{procedure_id}", response_model=ProcedureDetail)
def procedure_detail(
    procedure_id: int,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """The guide: short explanation, the checklist, and your plans for it."""
    p = crud.get_procedure(db, procedure_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such procedure")
    lang = user.language
    return ProcedureDetail(
        id=p.id, code=p.code, name=localized(p, "name", lang), summary=localized(p, "summary", lang),
        steps=[ProcedureStepOut(id=s.id, position=s.position, text=localized(s, "text", lang),
                                hours_before=s.hours_before) for s in p.steps],
        plans=[plan_out(plan, lang) for plan in crud.user_plans(db, user.id, p.id)],
    )


@app.post("/api/procedures/{procedure_id}/plans", response_model=PrepPlanOut,
          status_code=status.HTTP_201_CREATED)
def create_prep_plan(
    procedure_id: int,
    data: PrepPlanCreate,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """"Set reminder": the appointment time, and which checklist lines to be reminded about."""
    p = crud.get_procedure(db, procedure_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such procedure")
    step_ids = {s.id for s in p.steps}
    if any(r.step_id not in step_ids for r in data.reminders):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown checklist step")
    if data.appointment_at < datetime.now():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The appointment is in the past")
    return plan_out(crud.create_plan(db, user, p, data.appointment_at, data.reminders), user.language)


@app.get("/api/prep-plans", response_model=list[PrepPlanOut])
def prep_plans(
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Your upcoming preparations, soonest first."""
    return [plan_out(p, user.language) for p in crud.user_plans(db, user.id)]


@app.patch("/api/prep-items/{item_id}", response_model=PrepPlanItemOut)
def tick_prep_item(
    item_id: int,
    data: ItemChecked,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Tick or untick a checklist line. Ticking cancels its pending reminder."""
    item = crud.get_plan_item(db, user.id, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such checklist item")
    item = crud.set_item_checked(db, item, data.checked)
    return PrepPlanItemOut(id=item.id, step_id=item.step_id,
                           text=localized(item.step, "text", user.language),
                           checked=item.checked, remind_at=item.remind_at, sent_at=item.sent_at)


@app.delete("/api/prep-plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_prep_plan(
    plan_id: int,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    plan = crud.get_plan(db, user.id, plan_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such plan")
    crud.delete_plan(db, plan)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------
# notifications
#
# Every route requires a login. An unauthenticated send endpoint is an open
# SMS relay - anyone who finds the URL could run up the Twilio bill.
# --------------------------------------------------------------------------

@app.get("/api/notifications", response_model=Inbox)
def my_notifications(
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """The inbox: every in-app reminder, newest first."""
    return Inbox(
        waiting=crud.waiting_count(db, user.id),
        items=[NotificationItem.model_validate(n) for n in crud.inbox(db, user.id)],
    )


@app.get("/api/reminders/pending", response_model=list[PopupOut])
def pending_reminders(
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Reminders still waiting for Accept - the app pops these up until accepted."""
    return [popup_out(db, n) for n in crud.pending_popups(db, user.id)]


@app.post("/api/notifications/{notification_id}/accept", status_code=status.HTTP_204_NO_CONTENT)
def accept_notification(
    notification_id: int,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Accept a reminder (and the earlier ones about the same item). It still
    comes back tomorrow if the item is not done by then."""
    crud.accept(db, user.id, notification_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/notifications/accept-all", status_code=status.HTTP_204_NO_CONTENT)
def accept_all(
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    crud.accept(db, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/notifications/check", response_model=ReminderRunOut)
async def check_my_reminders(
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Run the reminder check for yourself now instead of waiting for the loop.

    Same rules as the loop (push/SMS once a day, email once per due date),
    so pressing it twice does not send twice.
    """
    now = datetime.now()
    report = await reminders.remind_user(db, user, now, force=True)
    await reminders.send_prep_reminders(db, now, report, user_id=user.id)
    return ReminderRunOut(**vars(report))


@app.get("/api/notifications/recipients", response_model=RecipientCount)
def notification_recipients(
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """How many users can be texted, so the page can say so before sending."""
    return RecipientCount(recipients=crud.count_users_with_phone(db))


@app.post("/api/notifications/send", response_model=NotificationOut)
async def send_notification(
    data: NotificationCreate,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Broadcast: text every user who has a phone number saved.

    Numbers that cannot be normalized are skipped and reported by name - one
    unusable number must not cost everyone else their message.
    """
    recipients = crud.users_with_phone(db)
    if not recipients:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No user has a phone number saved")

    # Normalize first, so we know who is actually sendable before we call out.
    results: list[RecipientResult] = []
    sendable: list[tuple[int, str]] = []

    for person in recipients:
        name = f"{person.name} {person.surname or ''}".strip()
        try:
            number = notifications.normalize_phone(person.phone, person.country)
        except ValueError as exc:
            results.append(RecipientResult(
                user_id=person.id, name=name, phone=person.phone,
                status="skipped", detail=str(exc),
            ))
            continue
        sendable.append((person.id, number))
        results.append(RecipientResult(user_id=person.id, name=name, phone=number, status="pending"))

    outcomes = await notifications.send_batch([n for _, n in sendable], data.message)

    by_user = {user_id: outcome for (user_id, _), outcome in zip(sendable, outcomes)}
    for result in results:
        outcome = by_user.get(result.user_id)
        if outcome is not None:
            result.status = outcome["status"]
            result.detail = outcome["detail"]
        crud.add_notification(
            db, user_id=result.user_id, channel="sms", kind="broadcast",
            message=data.message, status=result.status, detail=result.detail,
        )
    db.commit()

    return NotificationOut(
        dry_run=not notifications.is_configured(),
        sent=sum(1 for r in results if r.status in ("sent", "dry_run")),
        skipped=sum(1 for r in results if r.status == "skipped"),
        failed=sum(1 for r in results if r.status == "failed"),
        results=results,
    )


# --------------------------------------------------------------------------
# static frontend
#
# Mounted LAST on purpose: the /api routes above are matched first, and
# anything left over is served as a file from app/static/.
# html=True means "/" serves index.html.
# --------------------------------------------------------------------------
app.mount(
    "/",
    StaticFiles(directory=Path(__file__).parent / "static", html=True),
    name="static",
)
