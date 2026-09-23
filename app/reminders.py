"""reminders.py - the automatic side of notifications.

A background loop wakes up every REMINDER_EVERY_MINUTES, works out each
user's schedule, and nudges them about what is overdue or coming up:

  * push - a row in the notifications table, shown in the in-app inbox
  * sms  - one combined text per run, via notifications.send_batch()
           (dry run when Twilio is not configured, like the broadcast)

The user's "Notifications" setting decides how pushy that is:

  off       - nothing
  gentle    - overdue items, and items due within a week; at most once a
              month per item
  frequent  - overdue items, and everything in the due-soon window; at most
              once a week per item

"Remind me later" (a snooze) silences an item completely until it runs out.
Every reminder is written to the notifications table, and that table is also
what the cooldown reads - so restarting the server (or uvicorn --reload doing
it for you) never causes a second wave of messages.
"""
import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.orm import Session

import crud
import notifications
import planner
from database import SessionLocal
from models import User

load_dotenv(Path(__file__).parent / ".env")

# 0 turns the background loop off; POST /api/notifications/check still works.
EVERY_MINUTES = float(os.getenv("REMINDER_EVERY_MINUTES", "60"))

# style -> (remind about items due within N days, then wait N days before repeating)
STYLES = {
    "gentle": (7, 30),
    "frequent": (planner.DUE_SOON_DAYS, 7),
}

log = logging.getLogger(__name__)


@dataclass
class RunReport:
    users_checked: int = 0
    push: int = 0
    sms: int = 0
    dry_run: bool = field(default_factory=lambda: not notifications.is_configured())


# --------------------------------------------------------------------------
# deciding - pure, no database
# --------------------------------------------------------------------------

def pick_due(
    items: list[planner.ScheduleItem],
    style: str,
    reminded: dict[int, datetime],
    now: datetime,
) -> list[planner.ScheduleItem]:
    """The schedule items this user should hear about right now."""
    if style not in STYLES:
        return []
    window, cooldown = STYLES[style]

    due = []
    for item in items:
        if item.snoozed or item.days > window:
            continue
        last = reminded.get(item.checkup.id)
        if last is not None and now - last < timedelta(days=cooldown):
            continue
        due.append(item)
    return due


def kind_of(item: planner.ScheduleItem) -> str:
    return "overdue" if item.status == "overdue" else "due_soon"


def push_text(item: planner.ScheduleItem) -> str:
    name = item.checkup.name
    if item.last_done is None:
        return f"No record of your {name.lower()} yet - log it if you've had one, or book it."
    if item.status == "overdue":
        return f"{name} is {planner.describe(item)}. Book it, or log it if you already went."
    return f"{name} is {planner.describe(item)}."


def sms_text(user: User, items: list[planner.ScheduleItem]) -> str:
    """One text for the whole batch - five separate SMS would be spam."""
    parts = []
    for item in items:
        if item.last_done is None:
            parts.append(f"{item.checkup.name}: no record yet")
        else:
            parts.append(f"{item.checkup.name}: {planner.describe(item)}")
    return (
        f"Hi {user.name}, health check reminder - " + "; ".join(parts)
        + ". Open the app to log it or snooze."
    )


# --------------------------------------------------------------------------
# doing
# --------------------------------------------------------------------------

async def remind_user(
    db: Session,
    user: User,
    today: date,
    now: datetime,
    checkups: list | None = None,
    report: RunReport | None = None,
) -> RunReport:
    """Send whatever this one user is due. Commits its own rows."""
    report = report or RunReport()
    report.users_checked += 1

    items = crud.schedule_for(db, user, today, checkups)
    due = pick_due(items, user.reminder_style, crud.last_reminded(db, user.id), now)
    if not due:
        return report

    if user.remind_push:
        for item in due:
            crud.add_notification(
                db, user_id=user.id, checkup_type_id=item.checkup.id,
                channel="push", kind=kind_of(item), message=push_text(item),
                status="delivered",
            )
            report.push += 1

    if user.remind_sms:
        body = sms_text(user, due)
        try:
            number = notifications.normalize_phone(user.phone, user.country)
            outcome = await notifications.send_sms(number, body)
        except ValueError as exc:
            outcome = {"status": "skipped", "detail": str(exc)}

        # One row per item, so each item's cooldown starts now - the text
        # itself went out once.
        for item in due:
            crud.add_notification(
                db, user_id=user.id, checkup_type_id=item.checkup.id,
                channel="sms", kind=kind_of(item), message=body,
                status=outcome["status"], detail=outcome["detail"],
            )
        if outcome["status"] in ("sent", "dry_run"):
            report.sms += 1

    db.commit()
    return report


async def run_once(db: Session, today: date | None = None) -> RunReport:
    """One pass over every user who wants reminders."""
    today = today or date.today()
    now = datetime.now()
    checkups = crud.all_checkups(db)
    report = RunReport()

    for user in crud.users_to_remind(db):
        try:
            await remind_user(db, user, today, now, checkups, report)
        except Exception:
            # One user's bad data must not stop everyone else's reminders.
            db.rollback()
            log.exception("reminders failed for user %s", user.id)

    log.info(
        "reminder run: %d users, %d push, %d sms%s",
        report.users_checked, report.push, report.sms,
        " (dry run)" if report.dry_run else "",
    )
    return report


async def _loop(minutes: float) -> None:
    while True:
        try:
            with SessionLocal() as db:
                await run_once(db)
        except Exception:
            # Database down, etc. Log it and try again next time round -
            # the loop must never die quietly.
            log.exception("reminder run failed")
        await asyncio.sleep(minutes * 60)


def start() -> asyncio.Task | None:
    """Start the background loop. Called from main.py's lifespan."""
    if EVERY_MINUTES <= 0:
        log.info("reminder loop disabled (REMINDER_EVERY_MINUTES=0)")
        return None
    return asyncio.create_task(_loop(EVERY_MINUTES), name="reminders")
