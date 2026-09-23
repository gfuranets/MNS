"""crud.py - every database read/write lives here.

Routes in main.py stay thin: they validate input, call a function from this
file, and shape the response. No SQL in the route handlers.
"""
from datetime import date, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

import auth
import planner
from models import (
    CheckupType,
    LogEntry,
    Notification,
    RiskFactor,
    Snooze,
    User,
)
from schema import LogEntryCreate, ProfileUpdate, SettingsUpdate, UserCreate


# --------------------------------------------------------------------------
# users
# --------------------------------------------------------------------------

def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def create_user(db: Session, data: UserCreate) -> User:
    """Hash the password and insert the row.

    The caller is responsible for checking the email is free first -
    see the signup route in main.py.
    """
    user = User(
        email=data.email,
        password_hash=auth.hash_password(data.password),
        name=data.name,
        phone=data.phone or None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)  # reload so user.id and user.created_at are populated
    return user


def update_profile(db: Session, user: User, data: ProfileUpdate) -> User:
    """Onboarding step 2. Risk factors are replaced wholesale, not merged:
    unticking a box on the page must remove it here too."""
    user.birth_year = data.birth_year
    user.sex = data.sex
    user.country = data.country.strip()

    codes = set(data.risk_factors)
    other = (data.risk_other or "").strip()
    if other:
        codes.add("other")  # typing in the "Other" box counts as ticking it

    user.risk_factors = [
        RiskFactor(code=code, note=other if code == "other" and other else None)
        for code in sorted(codes)
    ]
    db.commit()
    db.refresh(user)
    return user


def update_settings(db: Session, user: User, data: SettingsUpdate) -> User:
    """Apply only the fields the client actually sent."""
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "phone":
            value = (value or "").strip() or None
        elif value is None:
            continue   # an explicit null for a NOT NULL setting means "unchanged"
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user: User) -> list[str]:
    """Delete the account and everything hanging off it (FKs cascade).

    Returns the attachment file names so the caller can remove the files -
    the database cannot do that part.
    """
    files = list(db.scalars(
        select(LogEntry.attachment_path)
        .where(LogEntry.user_id == user.id, LogEntry.attachment_path.is_not(None))
    ))
    db.delete(user)
    db.commit()
    return files


# --------------------------------------------------------------------------
# catalog + schedule
# --------------------------------------------------------------------------

def all_checkups(db: Session) -> list[CheckupType]:
    return list(db.scalars(select(CheckupType).order_by(CheckupType.name)))


def get_checkup(db: Session, checkup_id: int) -> CheckupType | None:
    return db.get(CheckupType, checkup_id)


def find_checkup_by_title(db: Session, title: str) -> CheckupType | None:
    """Match a free-text log title ("blood test ") to a catalog entry by name or code."""
    key = title.strip().casefold()
    for checkup in all_checkups(db):
        if key in (checkup.name.casefold(), checkup.code.replace("_", " ")):
            return checkup
    return None


def last_done_by_type(db: Session, user_id: int) -> dict[int, date]:
    rows = db.execute(
        select(LogEntry.checkup_type_id, func.max(LogEntry.done_on))
        .where(LogEntry.user_id == user_id, LogEntry.checkup_type_id.is_not(None))
        .group_by(LogEntry.checkup_type_id)
    )
    return {type_id: done for type_id, done in rows}


def snoozes_for(db: Session, user_id: int) -> dict[int, date]:
    rows = db.execute(
        select(Snooze.checkup_type_id, Snooze.until).where(Snooze.user_id == user_id)
    )
    return {type_id: until for type_id, until in rows}


def schedule_for(
    db: Session, user: User, today: date, checkups: list[CheckupType] | None = None
) -> list[planner.ScheduleItem]:
    """The user's full schedule. Pass `checkups` when looping over many users
    so the catalog is loaded once, not once per user."""
    return planner.build_schedule(
        user,
        checkups if checkups is not None else all_checkups(db),
        last_done_by_type(db, user.id),
        snoozes_for(db, user.id),
        today,
    )


def snooze(db: Session, user_id: int, checkup_id: int, until: date) -> None:
    row = db.get(Snooze, (user_id, checkup_id))
    if row is None:
        db.add(Snooze(user_id=user_id, checkup_type_id=checkup_id, until=until))
    else:
        row.until = until
    db.commit()


# --------------------------------------------------------------------------
# log
# --------------------------------------------------------------------------

def create_log_entry(
    db: Session, user: User, data: LogEntryCreate, checkup: CheckupType | None
) -> LogEntry:
    """Save a log entry. Logging an item also ends any "remind me later" on it -
    there is nothing left to remind about."""
    entry = LogEntry(
        user_id=user.id,
        checkup_type_id=checkup.id if checkup else None,
        title=data.title.strip(),
        done_on=data.done_on,
        notes=data.notes,
    )
    db.add(entry)
    if checkup:
        db.execute(delete(Snooze).where(
            Snooze.user_id == user.id, Snooze.checkup_type_id == checkup.id
        ))
    db.commit()
    db.refresh(entry)
    return entry


def list_log(db: Session, user_id: int, checkup_id: int | None = None) -> list[LogEntry]:
    query = select(LogEntry).where(LogEntry.user_id == user_id)
    if checkup_id is not None:
        query = query.where(LogEntry.checkup_type_id == checkup_id)
    return list(db.scalars(query.order_by(LogEntry.done_on.desc(), LogEntry.id.desc())))


def get_log_entry(db: Session, user_id: int, entry_id: int) -> LogEntry | None:
    """Scoped to the user: someone else's entry id behaves exactly like a missing one."""
    return db.scalar(
        select(LogEntry).where(LogEntry.id == entry_id, LogEntry.user_id == user_id)
    )


def delete_log_entry(db: Session, entry: LogEntry) -> None:
    db.delete(entry)
    db.commit()


def set_attachment(db: Session, entry: LogEntry, name: str, path: str) -> LogEntry:
    entry.attachment_name = name
    entry.attachment_path = path
    db.commit()
    db.refresh(entry)
    return entry


# --------------------------------------------------------------------------
# notifications
# --------------------------------------------------------------------------

def add_notification(
    db: Session,
    *,
    user_id: int,
    channel: str,
    kind: str,
    message: str,
    status: str,
    checkup_type_id: int | None = None,
    detail: str | None = None,
) -> Notification:
    """Record one notification. Does not commit - callers add a batch, then commit once."""
    row = Notification(
        user_id=user_id,
        checkup_type_id=checkup_type_id,
        channel=channel,
        kind=kind,
        message=message[:1000],
        status=status,
        detail=detail[:255] if detail else None,
    )
    db.add(row)
    return row


def inbox(db: Session, user_id: int, limit: int = 50) -> list[Notification]:
    return list(db.scalars(
        select(Notification)
        .where(Notification.user_id == user_id, Notification.channel == "push")
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
    ))


def unread_count(db: Session, user_id: int) -> int:
    return db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == user_id,
            Notification.channel == "push",
            Notification.read_at.is_(None),
        )
    ) or 0


def mark_read(db: Session, user_id: int, notification_id: int | None = None) -> int:
    """Mark one notification read, or all of them when no id is given.
    Returns how many rows changed."""
    query = update(Notification).where(
        Notification.user_id == user_id,
        Notification.channel == "push",
        Notification.read_at.is_(None),
    )
    if notification_id is not None:
        query = query.where(Notification.id == notification_id)
    changed = db.execute(query.values(read_at=datetime.now())).rowcount
    db.commit()
    return changed


def last_reminded(db: Session, user_id: int) -> dict[int, datetime]:
    """checkup_type_id -> when we last reminded this user about it, on any channel."""
    rows = db.execute(
        select(Notification.checkup_type_id, func.max(Notification.created_at))
        .where(
            Notification.user_id == user_id,
            Notification.checkup_type_id.is_not(None),
            Notification.kind.in_(("overdue", "due_soon")),
        )
        .group_by(Notification.checkup_type_id)
    )
    return {type_id: when for type_id, when in rows}


def users_to_remind(db: Session) -> list[User]:
    """Users who want reminders on at least one channel and have a profile to plan from."""
    return list(db.scalars(
        select(User).where(
            User.reminder_style != "off",
            (User.remind_push.is_(True)) | (User.remind_sms.is_(True)),
            User.birth_year.is_not(None),
        ).order_by(User.id)
    ))


# Phone numbers come from signup/settings, so "who can be texted" by a
# broadcast is simply everyone who filled that optional field in.
_HAS_PHONE = (User.phone.is_not(None), User.phone != "")


def users_with_phone(db: Session) -> list[User]:
    """Every user who can receive an SMS, oldest account first."""
    return list(db.scalars(select(User).where(*_HAS_PHONE).order_by(User.id)))


def count_users_with_phone(db: Session) -> int:
    """How many users have a phone number, without loading them all."""
    return db.scalar(select(func.count(User.id)).where(*_HAS_PHONE)) or 0
