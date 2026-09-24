"""crud.py - every database read/write lives here.

Routes in main.py stay thin: they validate input, call a function from this
file, and shape the response. No SQL in the route handlers.
"""
from datetime import date, datetime, timedelta

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session, contains_eager

import auth
import planner
from models import (
    CheckupType,
    LabReport,
    LabResult,
    LogEntry,
    Notification,
    PrepPlan,
    PrepPlanItem,
    Procedure,
    RiskFactor,
    Task,
    TaskEvent,
    User,
)
from schema import LogEntryCreate, PrepReminder, ProfileUpdate, SettingsUpdate, TaskCreate, UserCreate


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
        name=data.name.strip(),
        surname=data.surname.strip(),
        phone=(data.phone or "").strip() or None,
        language=data.language,
    )
    db.add(user)
    db.commit()
    db.refresh(user)  # reload so user.id and user.created_at are populated
    return user


def update_profile(db: Session, user: User, data: ProfileUpdate) -> User:
    """Personal data and risk factors. Risk factors are replaced wholesale,
    not merged: unticking a box on the page must remove it here too."""
    user.name = data.name.strip()
    user.surname = data.surname.strip()
    user.birth_date = data.birth_date
    user.sex = data.sex
    user.country = data.country.strip()
    user.phone = (data.phone or "").strip() or None

    risks = {}
    for r in data.risk_factors:
        note = (r.note or "").strip() or None
        if r.code == "other" and not note:
            continue   # an empty "Other" box says nothing
        risks[(r.code, r.scope)] = RiskFactor(
            code=r.code, scope=r.scope, note=note if r.code == "other" else None
        )
    user.risk_factors = list(risks.values())

    db.commit()
    db.refresh(user)
    return user


def give_consent(db: Session, user: User) -> User:
    if user.consent_at is None:
        user.consent_at = datetime.now()
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
# catalog
# --------------------------------------------------------------------------

def all_checkups(db: Session) -> list[CheckupType]:
    return list(db.scalars(select(CheckupType).order_by(CheckupType.name)))


def lab_results(db: Session, user_id: int) -> list[LabResult]:
    """Every measured value of the user, oldest draw first."""
    return list(db.scalars(
        select(LabResult)
        .join(LabResult.report)
        .options(contains_eager(LabResult.report))
        .where(LabReport.user_id == user_id)
        .order_by(LabReport.taken_at, LabResult.id)
    ).unique())


def lab_reports_by_log_entry(db: Session, user_id: int) -> dict[int, int]:
    """log_entry_id -> lab report id, for "See results" on the Log screen."""
    return dict(db.execute(
        select(LabReport.log_entry_id, LabReport.id)
        .where(LabReport.user_id == user_id, LabReport.log_entry_id.is_not(None))
    ).all())


def get_checkup(db: Session, checkup_id: int) -> CheckupType | None:
    return db.get(CheckupType, checkup_id)


def find_checkup_by_title(db: Session, title: str) -> CheckupType | None:
    """Match a free-text title ("blood test ", "Asins analīzes") to the catalog."""
    key = title.strip().casefold()
    for checkup in all_checkups(db):
        names = {checkup.name.casefold(), (checkup.name_lv or "").casefold(),
                 checkup.code.replace("_", " ")}
        if key in names:
            return checkup
    return None


# --------------------------------------------------------------------------
# the schedule: recommended checks + the user's own tasks
# --------------------------------------------------------------------------

def last_done_by_type(db: Session, user_id: int) -> dict[int, date]:
    rows = db.execute(
        select(LogEntry.checkup_type_id, func.max(LogEntry.done_on))
        .where(LogEntry.user_id == user_id, LogEntry.checkup_type_id.is_not(None))
        .group_by(LogEntry.checkup_type_id)
    )
    return {type_id: done for type_id, done in rows}


def last_done_by_task(db: Session, user_id: int) -> dict[int, date]:
    rows = db.execute(
        select(TaskEvent.task_id, func.max(TaskEvent.done_on))
        .where(TaskEvent.user_id == user_id, TaskEvent.status == "done")
        .group_by(TaskEvent.task_id)
    )
    return {task_id: done for task_id, done in rows}


def pending_events(db: Session, user_id: int) -> list[TaskEvent]:
    return list(db.scalars(
        select(TaskEvent)
        .where(TaskEvent.user_id == user_id, TaskEvent.status == "pending")
        .order_by(TaskEvent.due_on)
    ))


def all_items(
    db: Session, user: User, today: date, checkups: list[CheckupType] | None = None
) -> list[planner.Item]:
    """Everything on the user's schedule, most urgent first. Pass `checkups`
    when looping over many users so the catalog is loaded once."""
    guidelines = planner.guideline_items(
        user, checkups if checkups is not None else all_checkups(db),
        last_done_by_type(db, user.id), today, user.language,
    )
    tasks = planner.task_items(pending_events(db, user.id), last_done_by_task(db, user.id), today)
    return planner.sort_items(guidelines + tasks)


# --------------------------------------------------------------------------
# tasks (the Add screen)
# --------------------------------------------------------------------------

def create_task(db: Session, user: User, data: TaskCreate) -> Task:
    """A repeating task starts with one occurrence; the next is created when
    that one is finished. A manual task gets all its dates up front."""
    task = Task(
        user_id=user.id,
        title=data.title.strip(),
        category=data.category,
        description=data.description,
        doctor_name=(data.doctor_name or "").strip() or None,
        doctor_specialty=(data.doctor_specialty or "").strip() or None,
        repeat_every=data.repeat_every,
        repeat_unit=data.repeat_unit,
        remind_every_minutes=data.remind_every_minutes,
    )
    for due in sorted({data.first_date, *data.extra_dates}):
        task.events.append(TaskEvent(user_id=user.id, due_on=due))
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def list_tasks(db: Session, user_id: int) -> list[Task]:
    return list(db.scalars(
        select(Task).where(Task.user_id == user_id).order_by(Task.created_at.desc())
    ))


def get_task(db: Session, user_id: int, task_id: int) -> Task | None:
    """Scoped to the user: someone else's id behaves exactly like a missing one."""
    return db.scalar(select(Task).where(Task.id == task_id, Task.user_id == user_id))


def delete_task(db: Session, task: Task) -> None:
    db.delete(task)
    db.commit()


def add_task_date(db: Session, task: Task, due_on: date) -> TaskEvent:
    existing = next((e for e in task.events if e.due_on == due_on), None)
    if existing:
        return existing
    event = TaskEvent(task_id=task.id, user_id=task.user_id, due_on=due_on)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def get_event(db: Session, user_id: int, event_id: int) -> TaskEvent | None:
    return db.scalar(
        select(TaskEvent).where(TaskEvent.id == event_id, TaskEvent.user_id == user_id)
    )


def finish_event(
    db: Session, event: TaskEvent, status: str, done_on: date | None = None,
    notes: str | None = None,
) -> tuple[LogEntry | None, date | None]:
    """Mark an occurrence done or missed.

    Done also writes a log entry, so the Log and the vaccination passport see
    it. Either way a repeating task gets its next occurrence, and any reminder
    about this one is cleared. Returns (log entry or None, next due date).
    """
    task = event.task
    event.status = status
    entry = None
    if status == "done":
        event.done_on = done_on or date.today()
        entry = LogEntry(
            user_id=event.user_id, task_id=task.id, title=task.title,
            category=task.category, done_on=event.done_on, notes=notes,
        )
        if task.category == "vaccination" and task.repeats:
            entry.renew_on = planner.add_interval(event.done_on, task.repeat_every, task.repeat_unit)
        db.add(entry)

    next_due = planner.next_occurrence(event.due_on, task.repeat_every, task.repeat_unit)
    if next_due is not None:
        # Never schedule the next one in the past: a long-missed weekly task
        # continues from today rather than creating a pile of instant misses.
        while next_due < date.today():
            next_due = planner.add_interval(next_due, task.repeat_every, task.repeat_unit)
        if not any(e.due_on == next_due for e in task.events):
            db.add(TaskEvent(task_id=task.id, user_id=task.user_id, due_on=next_due))

    clear_item_reminders(db, event.user_id, task_event_id=event.id, commit=False)
    db.commit()
    if entry is not None:
        db.refresh(entry)
    return entry, next_due


# --------------------------------------------------------------------------
# log
# --------------------------------------------------------------------------

def create_log_entry(
    db: Session, user: User, data: LogEntryCreate, checkup: CheckupType | None
) -> LogEntry:
    """Save a log entry. Logging a recommended check clears its reminders -
    there is nothing left to remind about."""
    entry = LogEntry(
        user_id=user.id,
        checkup_type_id=checkup.id if checkup else None,
        title=data.title.strip(),
        category=checkup.category if checkup else data.category,
        done_on=data.done_on,
        renew_on=data.renew_on,
        notes=data.notes,
    )
    db.add(entry)
    if checkup:
        clear_item_reminders(db, user.id, checkup_type_id=checkup.id, commit=False)
    db.commit()
    db.refresh(entry)
    return entry


def list_log(db: Session, user_id: int, checkup_id: int | None = None) -> list[LogEntry]:
    query = select(LogEntry).where(LogEntry.user_id == user_id)
    if checkup_id is not None:
        query = query.where(LogEntry.checkup_type_id == checkup_id)
    return list(db.scalars(query.order_by(LogEntry.done_on.desc(), LogEntry.id.desc())))


def missed_events(db: Session, user_id: int) -> list[TaskEvent]:
    return list(db.scalars(
        select(TaskEvent).where(TaskEvent.user_id == user_id, TaskEvent.status == "missed")
    ))


def categories(db: Session, user: User, items: list[planner.Item]) -> list[str]:
    """Every category the user has anything in: logged, planned or recommended."""
    found = {i.category for i in items}
    found |= set(db.scalars(select(LogEntry.category).where(LogEntry.user_id == user.id).distinct()))
    found |= set(db.scalars(select(Task.category).where(Task.user_id == user.id).distinct()))
    return sorted(found)


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
# procedures + preparation plans
# --------------------------------------------------------------------------

def search_procedures(db: Session, q: str = "") -> list[Procedure]:
    """Case-insensitive search over both languages (the column collation is _ci)."""
    query = select(Procedure).order_by(Procedure.name)
    q = q.strip()
    if q:
        like = f"%{q}%"
        query = query.where(or_(
            Procedure.name.like(like), Procedure.name_lv.like(like),
            Procedure.keywords.like(like), Procedure.summary.like(like),
            Procedure.summary_lv.like(like),
        ))
    return list(db.scalars(query))


def get_procedure(db: Session, procedure_id: int) -> Procedure | None:
    return db.get(Procedure, procedure_id)


def procedure_ids_by_code(db: Session) -> dict[str, int]:
    return dict(db.execute(select(Procedure.code, Procedure.id)).all())


def create_plan(
    db: Session, user: User, procedure: Procedure, appointment_at: datetime,
    reminders: list[PrepReminder],
) -> PrepPlan:
    """Every step goes on the checklist; the chosen ones also get a reminder,
    by default hours_before the appointment (1 hour if the step has none)."""
    wanted = {r.step_id: r.remind_at for r in reminders}
    plan = PrepPlan(user_id=user.id, procedure_id=procedure.id, appointment_at=appointment_at)
    for step in procedure.steps:
        remind_at = None
        if step.id in wanted:
            remind_at = wanted[step.id] or appointment_at - timedelta(hours=step.hours_before or 1)
        plan.items.append(PrepPlanItem(step_id=step.id, remind_at=remind_at))
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def user_plans(
    db: Session, user_id: int, procedure_id: int | None = None, upcoming_only: bool = True,
) -> list[PrepPlan]:
    query = select(PrepPlan).where(PrepPlan.user_id == user_id)
    if procedure_id is not None:
        query = query.where(PrepPlan.procedure_id == procedure_id)
    if upcoming_only:
        # Keep a plan around for a day after the appointment ("drink water after").
        query = query.where(PrepPlan.appointment_at >= datetime.now() - timedelta(days=1))
    return list(db.scalars(query.order_by(PrepPlan.appointment_at)))


def get_plan(db: Session, user_id: int, plan_id: int) -> PrepPlan | None:
    return db.scalar(select(PrepPlan).where(PrepPlan.id == plan_id, PrepPlan.user_id == user_id))


def get_plan_item(db: Session, user_id: int, item_id: int) -> PrepPlanItem | None:
    return db.scalar(
        select(PrepPlanItem).join(PrepPlan)
        .where(PrepPlanItem.id == item_id, PrepPlan.user_id == user_id)
    )


def set_item_checked(db: Session, item: PrepPlanItem, checked: bool) -> PrepPlanItem:
    """Ticking a line also means its reminder is no longer needed."""
    item.checked = checked
    if checked:
        clear_item_reminders(db, item.plan.user_id, prep_item_id=item.id, commit=False)
    db.commit()
    db.refresh(item)
    return item


def delete_plan(db: Session, plan: PrepPlan) -> None:
    db.delete(plan)
    db.commit()


def due_prep_items(db: Session, now: datetime) -> list[PrepPlanItem]:
    """Prep reminders whose time has come and that have not gone out yet."""
    return list(db.scalars(
        select(PrepPlanItem).where(
            PrepPlanItem.sent_at.is_(None),
            PrepPlanItem.remind_at.is_not(None),
            PrepPlanItem.remind_at <= now,
            PrepPlanItem.checked.is_(False),
        ).order_by(PrepPlanItem.remind_at)
    ))


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
    task_event_id: int | None = None,
    prep_item_id: int | None = None,
    due_on: date | None = None,
    detail: str | None = None,
) -> Notification:
    """Record one notification. Does not commit - callers add a batch, then commit once."""
    row = Notification(
        user_id=user_id,
        checkup_type_id=checkup_type_id,
        task_event_id=task_event_id,
        prep_item_id=prep_item_id,
        due_on=due_on,
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


def _waiting(user_id: int):
    return (
        Notification.user_id == user_id,
        Notification.channel == "push",
        Notification.accepted_at.is_(None),
    )


def waiting_count(db: Session, user_id: int) -> int:
    """Reminders not accepted yet - one per item, however many days it has nagged."""
    return len(pending_popups(db, user_id, limit=1000))


def pending_popups(db: Session, user_id: int, limit: int = 20) -> list[Notification]:
    """The newest un-accepted reminder for each item, newest first."""
    rows = db.scalars(
        select(Notification).where(*_waiting(user_id))
        .order_by(Notification.created_at.desc(), Notification.id.desc())
    )
    seen, popups = set(), []
    for row in rows:
        target = (row.checkup_type_id, row.task_event_id, row.prep_item_id)
        if target in seen:
            continue
        seen.add(target)
        popups.append(row)
        if len(popups) >= limit:
            break
    return popups


def accept(db: Session, user_id: int, notification_id: int | None = None) -> int:
    """Accept one reminder - and every earlier one about the same item - or,
    with no id, everything. Returns how many rows changed."""
    query = update(Notification).where(*_waiting(user_id))
    if notification_id is not None:
        row = db.scalar(select(Notification).where(
            Notification.id == notification_id, Notification.user_id == user_id
        ))
        if row is None:
            return 0
        query = query.where(
            Notification.checkup_type_id.is_(None) if row.checkup_type_id is None
            else Notification.checkup_type_id == row.checkup_type_id,
            Notification.task_event_id.is_(None) if row.task_event_id is None
            else Notification.task_event_id == row.task_event_id,
            Notification.prep_item_id.is_(None) if row.prep_item_id is None
            else Notification.prep_item_id == row.prep_item_id,
        )
    changed = db.execute(query.values(accepted_at=datetime.now())).rowcount
    db.commit()
    return changed


def clear_item_reminders(
    db: Session, user_id: int, *, checkup_type_id: int | None = None,
    task_event_id: int | None = None, prep_item_id: int | None = None, commit: bool = True,
) -> None:
    """Marking something done deletes the reminders still waiting about it."""
    target = (
        Notification.checkup_type_id == checkup_type_id if checkup_type_id is not None
        else Notification.task_event_id == task_event_id if task_event_id is not None
        else Notification.prep_item_id == prep_item_id
    )
    db.execute(delete(Notification).where(*_waiting(user_id), target))
    if commit:
        db.commit()


def last_reminded(db: Session, user_id: int) -> dict[tuple[str, int], datetime]:
    """(kind, id) -> when we last reminded this user about that item by push
    or SMS. Emails have their own rule - see last_emailed()."""
    found = {}
    for column, kind in ((Notification.checkup_type_id, "guideline"),
                         (Notification.task_event_id, "task")):
        rows = db.execute(
            select(column, func.max(Notification.created_at))
            .where(Notification.user_id == user_id, column.is_not(None),
                   Notification.channel != "email",
                   Notification.kind.in_(("overdue", "due_soon")))
            .group_by(column)
        )
        found.update({(kind, item_id): when for item_id, when in rows})
    return found


def last_emailed(db: Session, user_id: int) -> dict[tuple[str, int, date | None], datetime]:
    """(kind, id, due_on) -> when this user was last emailed about that item
    for that due date. Failed sends do not count, so they are retried."""
    found = {}
    for column, kind in ((Notification.checkup_type_id, "guideline"),
                         (Notification.task_event_id, "task")):
        rows = db.execute(
            select(column, Notification.due_on, func.max(Notification.created_at))
            .where(Notification.user_id == user_id, Notification.channel == "email",
                   column.is_not(None), Notification.status.in_(("sent", "dry_run")))
            .group_by(column, Notification.due_on)
        )
        found.update({(kind, item_id, due_on): when for item_id, due_on, when in rows})
    return found


def users_to_remind(db: Session) -> list[User]:
    """Users who want daily reminders on at least one channel and have a
    profile to plan from."""
    return list(db.scalars(
        select(User).where(
            User.reminders_on.is_(True),
            (User.remind_push.is_(True)) | (User.remind_sms.is_(True))
            | (User.remind_email.is_(True)),
            User.birth_date.is_not(None),
        ).order_by(User.id)
    ))


# Phone numbers come from signup/profile, so "who can be texted" by a
# broadcast is simply everyone who filled that optional field in.
_HAS_PHONE = (User.phone.is_not(None), User.phone != "")


def users_with_phone(db: Session) -> list[User]:
    """Every user who can receive an SMS, oldest account first."""
    return list(db.scalars(select(User).where(*_HAS_PHONE).order_by(User.id)))


def count_users_with_phone(db: Session) -> int:
    """How many users have a phone number, without loading them all."""
    return db.scalar(select(func.count(User.id)).where(*_HAS_PHONE)) or 0
