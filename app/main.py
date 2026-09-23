"""main.py - the FastAPI app: API routes plus the static frontend.

Routes stay thin. They validate input (Pydantic does that automatically),
call crud/auth/planner, and return a schema. No SQL lives in this file.
"""
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
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
from models import User
from schema import (
    CheckupDetail,
    CheckupTypeOut,
    Counts,
    HomeOut,
    Inbox,
    LogEntryCreate,
    LogEntryOut,
    MarkDone,
    NotificationCreate,
    NotificationOut,
    PrepGuide,
    ProfileUpdate,
    RecipientCount,
    RecipientResult,
    ReminderRunOut,
    ScheduleItemOut,
    SettingsUpdate,
    SnoozeCreate,
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


def item_out(item: planner.ScheduleItem) -> ScheduleItemOut:
    """planner.ScheduleItem -> the JSON shape shared by home, schedule and detail."""
    c = item.checkup
    return ScheduleItemOut(
        id=c.id, code=c.code, name=c.name, category=c.category, coverage=c.coverage,
        status=item.status, status_text=planner.describe(item),
        interval_months=item.interval_months, last_done=item.last_done,
        due_on=item.due_on, days=item.days, snoozed_until=item.snoozed_until,
    )


def find_item(db: Session, user: User, checkup_id: int) -> planner.ScheduleItem:
    """The schedule entry for one checkup, or 404 if it does not apply to this user."""
    for item in crud.schedule_for(db, user, date.today()):
        if item.checkup.id == checkup_id:
            return item
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Not on your schedule")


# --------------------------------------------------------------------------
# user system
# --------------------------------------------------------------------------

@app.post("/api/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(data: UserCreate, db: Session = Depends(get_db)):
    """Create an account. Returns the new user (never the password hash)."""
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
    """The logged-in user's profile. Requires `Authorization: Bearer <token>`.

    `profile_complete: false` means onboarding step 2 has not been done yet.
    """
    return user


@app.put("/api/me/profile", response_model=UserOut)
def set_profile(
    data: ProfileUpdate,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Onboarding step 2: birth year, sex, country, and optional risk factors."""
    return crud.update_profile(db, user, data)


@app.patch("/api/me/settings", response_model=UserOut)
def set_settings(
    data: SettingsUpdate,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Notifications, reminder channels, language, phone. Send only what changed."""
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
    """Privacy & data: everything we hold about you, as one JSON download."""
    return {
        "profile": UserOut.model_validate(user).model_dump(mode="json"),
        "log": [
            LogEntryOut.model_validate(e).model_dump(mode="json")
            for e in crud.list_log(db, user.id)
        ],
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
    """Privacy & data: delete the account, the log, and uploaded files."""
    for name in crud.delete_user(db, user):
        (UPLOAD_DIR / name).unlink(missing_ok=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------
# home + schedule
# --------------------------------------------------------------------------

@app.get("/api/home", response_model=HomeOut)
def home(
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """The home screen in one call: counts, the urgent card, and what is coming up."""
    items = crud.schedule_for(db, user, date.today())
    by_status = {s: [i for i in items if i.status == s] for s in planner.STATUS_ORDER}

    # The red card is the most overdue item the user has not asked us to hold off on.
    urgent = next((i for i in by_status["overdue"] if not i.snoozed), None)

    return HomeOut(
        name=user.name,
        profile_complete=user.profile_complete,
        counts=Counts(**{s: len(v) for s, v in by_status.items()}),
        urgent=item_out(urgent) if urgent else None,
        coming_up=[item_out(i) for i in by_status["due_soon"]],
        unread_notifications=crud.unread_count(db, user.id),
    )


@app.get("/api/schedule", response_model=list[ScheduleItemOut])
def schedule(
    coverage: str = "all",
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Every item that applies to you, most urgent first.

    coverage = all | state | private - the filter chips on the schedule page.
    Group by `status` for the Overdue / Due soon / Up to date sections.
    """
    if coverage not in ("all", "state", "private"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "coverage must be all, state or private")
    items = crud.schedule_for(db, user, date.today())
    return [
        item_out(i) for i in items
        if coverage == "all" or i.checkup.coverage == coverage
    ]


@app.get("/api/checkup-types", response_model=list[CheckupTypeOut])
def checkup_types(
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """The whole catalog - for the "What did you do?" picker when logging."""
    return crud.all_checkups(db)


@app.get("/api/checkups/{checkup_id}", response_model=CheckupDetail)
def checkup_detail(
    checkup_id: int,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Item detail: status, guideline text, "more info", prep guide and your history."""
    item = find_item(db, user, checkup_id)
    c = item.checkup
    return CheckupDetail(
        **item_out(item).model_dump(),
        summary=c.summary, more_info=c.more_info,
        preparation=c.preparation, source_url=c.source_url,
        history=crud.list_log(db, user.id, checkup_id),
    )


@app.post("/api/checkups/{checkup_id}/done", response_model=LogEntryOut,
          status_code=status.HTTP_201_CREATED)
def mark_done(
    checkup_id: int,
    data: MarkDone,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """"Mark as done" - a log entry for this item, today unless a date is given."""
    checkup = crud.get_checkup(db, checkup_id)
    if checkup is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such checkup")
    entry = LogEntryCreate(
        title=checkup.name, done_on=data.done_on or date.today(),
        checkup_type_id=checkup.id, notes=data.notes,
    )
    return crud.create_log_entry(db, user, entry, checkup)


@app.post("/api/checkups/{checkup_id}/snooze", response_model=ScheduleItemOut)
def snooze(
    checkup_id: int,
    data: SnoozeCreate,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """"Remind me later" - no reminders about this item for `days` days (default 30)."""
    find_item(db, user, checkup_id)  # 404 if it is not on this user's schedule
    crud.snooze(db, user.id, checkup_id, date.today() + timedelta(days=data.days))
    return item_out(find_item(db, user, checkup_id))


@app.get("/api/prep", response_model=list[PrepGuide])
def prep(
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """The Prep tab: preparation guides for what is overdue or due soon."""
    return [
        PrepGuide(
            id=i.checkup.id, name=i.checkup.name, status=i.status,
            status_text=planner.describe(i), preparation=i.checkup.preparation,
        )
        for i in crud.schedule_for(db, user, date.today())
        if i.status != "up_to_date" and i.checkup.preparation
    ]


@app.get("/api/vaccinations", response_model=list[VaccinationOut])
def vaccination_passport(
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """The vaccination passport: each recommended vaccine, every logged dose, next due."""
    log = crud.list_log(db, user.id)
    return [
        VaccinationOut(
            id=i.checkup.id, name=i.checkup.name, last_done=i.last_done,
            due_on=i.due_on, status=i.status,
            doses=[e.done_on for e in log if e.checkup_type_id == i.checkup.id],
        )
        for i in crud.schedule_for(db, user, date.today())
        if i.checkup.category == "vaccination"
    ]


# --------------------------------------------------------------------------
# log
# --------------------------------------------------------------------------

@app.get("/api/log", response_model=list[LogEntryOut])
def list_log(
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Everything you have logged, newest first."""
    return crud.list_log(db, user.id)


@app.post("/api/log", response_model=LogEntryOut, status_code=status.HTTP_201_CREATED)
def create_log(
    data: LogEntryCreate,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """"Log an entry". done_on may be in the past - backdating is the normal case."""
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
    """"Add photo or PDF" - multipart upload, one file per entry (a new one replaces it)."""
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
    """The in-app inbox (push reminders), newest first."""
    return Inbox(unread=crud.unread_count(db, user.id), items=crud.inbox(db, user.id))


@app.post("/api/notifications/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def read_notification(
    notification_id: int,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    crud.mark_read(db, user.id, notification_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT)
def read_all_notifications(
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    crud.mark_read(db, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/notifications/check", response_model=ReminderRunOut)
async def check_my_reminders(
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Run the reminder check for yourself now instead of waiting for the loop.

    Same rules as the background loop - including the cooldown, so pressing
    it twice does not send twice.
    """
    report = await reminders.remind_user(db, user, date.today(), datetime.now())
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

    The request carries only the message. Recipients come from the database,
    and each number is normalized using the country that user registered with.

    Numbers that cannot be normalized are skipped and reported by name - one
    unusable number must not cost everyone else their message.
    """
    recipients = crud.users_with_phone(db)
    if not recipients:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No user has a phone number saved",
        )

    # Normalize first, so we know who is actually sendable before we call out.
    results: list[RecipientResult] = []
    sendable: list[tuple[int, str]] = []

    for person in recipients:
        try:
            number = notifications.normalize_phone(person.phone, person.country)
        except ValueError as exc:
            results.append(RecipientResult(
                user_id=person.id, name=person.name, phone=person.phone,
                status="skipped", detail=str(exc),
            ))
            continue
        sendable.append((person.id, number))
        results.append(RecipientResult(
            user_id=person.id, name=person.name, phone=number, status="pending",
        ))

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
