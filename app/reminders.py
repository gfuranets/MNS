"""reminders.py - the automatic side of notifications.

A background loop wakes up every REMINDER_EVERY_MINUTES and does two jobs:

1. Daily reminders. For every user with reminders on, anything on their
   schedule (recommended checks and their own tasks) that is late, or due
   within their `reminder_lead_days`, gets a reminder - once a day, every
   day, until it is marked done. They go out from REMINDER_SEND_HOUR (9:00)
   so nobody gets a text at midnight.

     push - a row in the notifications table. The app shows it as a pop-up
            that asks for Accept; until accepted it keeps popping up.
     sms  - one combined text per user per day, via notifications.send_batch()
            (dry run when Twilio is not configured, like the broadcast)

2. Preparation reminders. A step of a procedure checklist the user asked to
   be reminded about ("stop eating", "take your passport") goes out at its
   exact time, once.

Every reminder is written to the notifications table, and that table is what
"already reminded today?" reads - so restarting the server never causes a
second wave of messages.
"""
import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.orm import Session

import crud
import notifications
import planner
import texts
from database import SessionLocal
from models import User, localized

load_dotenv(Path(__file__).parent / ".env")

# 0 turns the background loop off; POST /api/notifications/check still works.
# Short by default so preparation reminders arrive close to their time.
EVERY_MINUTES = float(os.getenv("REMINDER_EVERY_MINUTES", "5"))
SEND_HOUR = int(os.getenv("REMINDER_SEND_HOUR", "9"))

log = logging.getLogger(__name__)


@dataclass
class RunReport:
    users_checked: int = 0
    push: int = 0
    sms: int = 0
    prep: int = 0
    dry_run: bool = field(default_factory=lambda: not notifications.is_configured())


# --------------------------------------------------------------------------
# deciding - pure, no database
# --------------------------------------------------------------------------

def pick_due(
    items: list[planner.Item],
    lead_days: int,
    reminded: dict[tuple[str, int], datetime],
    now: datetime,
) -> list[planner.Item]:
    """The items this user should hear about right now: late or due within
    `lead_days`, and not already reminded about today."""
    due = []
    for item in items:
        if item.days > lead_days:
            continue
        last = reminded.get(item.key)
        if last is not None and last.date() >= now.date():
            continue
        due.append(item)
    return due


def kind_of(item: planner.Item) -> str:
    return "overdue" if item.days < 0 else "due_soon"


# --------------------------------------------------------------------------
# doing
# --------------------------------------------------------------------------

async def _sms(user: User, body: str) -> dict:
    """Send one text to a user; never raises."""
    try:
        number = notifications.normalize_phone(user.phone, user.country)
    except ValueError as exc:
        return {"status": "skipped", "detail": str(exc)}
    return await notifications.send_sms(number, body)


async def remind_user(
    db: Session,
    user: User,
    now: datetime,
    checkups: list | None = None,
    report: RunReport | None = None,
    force: bool = False,
) -> RunReport:
    """Send whatever this one user is due today. Commits its own rows.

    force=True ignores the send hour and the reminders_on switch - used by
    "check now", where the user explicitly asked.
    """
    report = report or RunReport()
    if not force and (not user.reminders_on or now.hour < SEND_HOUR):
        return report
    report.users_checked += 1

    items = crud.all_items(db, user, now.date(), checkups)
    due = pick_due(items, user.reminder_lead_days, crud.last_reminded(db, user.id), now)
    if not due:
        return report

    def target(item):
        return ({"checkup_type_id": item.id} if item.kind == "guideline"
                else {"task_event_id": item.id})

    if user.remind_push:
        for item in due:
            crud.add_notification(
                db, user_id=user.id, channel="push", kind=kind_of(item),
                message=texts.push_text(item, user.language), status="delivered",
                **target(item),
            )
            report.push += 1

    if user.remind_sms:
        body = texts.sms_text(user.name, due, user.language)
        outcome = await _sms(user, body)
        # One row per item, so "already reminded today" works per item -
        # the text itself went out once.
        for item in due:
            crud.add_notification(
                db, user_id=user.id, channel="sms", kind=kind_of(item), message=body,
                status=outcome["status"], detail=outcome["detail"], **target(item),
            )
        if outcome["status"] in ("sent", "dry_run"):
            report.sms += 1

    db.commit()
    return report


async def send_prep_reminders(
    db: Session, now: datetime, report: RunReport, user_id: int | None = None,
) -> RunReport:
    """Every preparation step whose reminder time has come. Sent once each."""
    for item in crud.due_prep_items(db, now):
        plan = item.plan
        if user_id is not None and plan.user_id != user_id:
            continue
        user = crud.get_user_by_id(db, plan.user_id)
        lang = user.language
        body = texts.prep_text(
            localized(plan.procedure, "name", lang), plan.appointment_at,
            localized(item.step, "text", lang), lang,
        )
        # Explicitly requested, so it goes out even with daily reminders off -
        # but still only on the channels the user allows.
        if user.remind_push or not user.remind_sms:
            crud.add_notification(
                db, user_id=user.id, prep_item_id=item.id, channel="push",
                kind="prep", message=body, status="delivered",
            )
        if user.remind_sms:
            outcome = await _sms(user, body)
            crud.add_notification(
                db, user_id=user.id, prep_item_id=item.id, channel="sms", kind="prep",
                message=body, status=outcome["status"], detail=outcome["detail"],
            )
        item.sent_at = now
        report.prep += 1
        db.commit()
    return report


async def run_once(db: Session, now: datetime | None = None) -> RunReport:
    """One pass: preparation reminders, then everyone's daily reminders."""
    now = now or datetime.now()
    report = RunReport()

    try:
        await send_prep_reminders(db, now, report)
    except Exception:
        db.rollback()
        log.exception("preparation reminders failed")

    checkups = crud.all_checkups(db)
    for user in crud.users_to_remind(db):
        try:
            await remind_user(db, user, now, checkups, report)
        except Exception:
            # One user's bad data must not stop everyone else's reminders.
            db.rollback()
            log.exception("reminders failed for user %s", user.id)

    if report.push or report.sms or report.prep:
        log.info(
            "reminder run: %d users, %d push, %d sms, %d prep%s",
            report.users_checked, report.push, report.sms, report.prep,
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
