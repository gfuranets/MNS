"""schema.py - Pydantic models: the shape of data going in and out of the API.

Keep these separate from models.py. models.py describes the database;
schema.py describes the JSON contract. UserOut has no password_hash field,
so a hash can never leak out through a response even by accident.

Status texts ("due in 12 days") are NOT sent - the frontend builds them from
`days` / `last_done` in the user's language.
"""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

Sex = Literal["female", "male", "other"]
RiskCode = Literal["cancer", "diabetes", "heart", "other"]
RiskScope = Literal["personal", "family"]
Language = Literal["en", "lv"]
Status = Literal["overdue", "due_soon", "up_to_date"]
RepeatUnit = Literal["day", "week", "month", "year"]
Category = str   # free text: the Add screen offers defaults, users may type their own


def _not_in_future(d: date | None) -> date | None:
    if d is not None and d > date.today():
        raise ValueError("cannot be in the future")
    return d


def _clean_category(value: str) -> str:
    value = value.strip().lower()
    if not value:
        raise ValueError("choose a category")
    return value


# --------------------------------------------------------------------------
# users
# --------------------------------------------------------------------------

class UserCreate(BaseModel):
    """Body of POST /api/signup - onboarding step 1. Consent (step 2) and the
    health profile (step 3) come right after, on their own endpoints."""
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)  # bcrypt caps at 72 bytes
    name: str = Field(min_length=1, max_length=40)
    surname: str = Field(min_length=1, max_length=40)
    phone: str | None = Field(default=None, max_length=20)
    language: Language = "en"


class UserLogin(BaseModel):
    """Body of POST /api/login."""
    email: EmailStr
    password: str


class RiskFactorIn(BaseModel):
    code: RiskCode
    scope: RiskScope
    note: str | None = Field(default=None, max_length=200)


class RiskFactorOut(RiskFactorIn):
    model_config = ConfigDict(from_attributes=True)


class UserOut(BaseModel):
    """What the API returns about a user. Deliberately has no password field."""
    model_config = ConfigDict(from_attributes=True)  # lets us build it from a User row

    id: int
    email: EmailStr
    name: str
    surname: str | None
    birth_date: date | None
    sex: Sex | None
    country: str | None
    phone: str | None
    risk_factors: list[RiskFactorOut]
    language: Language
    reminders_on: bool
    reminder_lead_days: int
    remind_push: bool
    remind_sms: bool
    consent_at: datetime | None
    profile_complete: bool          # False -> the frontend continues onboarding
    created_at: datetime


class ProfileUpdate(BaseModel):
    """Body of PUT /api/me/profile - onboarding step 3, and Profile > Edit.

    Risk factors replace whatever was saved before.
    """
    name: str = Field(min_length=1, max_length=40)
    surname: str = Field(min_length=1, max_length=40)
    birth_date: date
    sex: Sex
    country: str = Field(min_length=1, max_length=40)
    phone: str | None = Field(default=None, max_length=20)
    risk_factors: list[RiskFactorIn] = []

    @field_validator("birth_date")
    @classmethod
    def plausible(cls, d: date) -> date:
        if d > date.today():
            raise ValueError("birth date cannot be in the future")
        if d.year < 1900:
            raise ValueError("check the birth year")
        return d


class SettingsUpdate(BaseModel):
    """Body of PATCH /api/me/settings. Every field is optional: send only what changed."""
    language: Language | None = None
    reminders_on: bool | None = None
    reminder_lead_days: int | None = Field(default=None, ge=0, le=60)
    remind_push: bool | None = None
    remind_sms: bool | None = None
    phone: str | None = Field(default=None, max_length=20)


class Token(BaseModel):
    """What POST /api/login returns."""
    access_token: str
    token_type: str = "bearer"


# --------------------------------------------------------------------------
# items: recommended checks and the user's own tasks, in one shape
# --------------------------------------------------------------------------

class ItemOut(BaseModel):
    """One thing on the schedule.

    kind = guideline -> id is a checkup type: open /api/checkups/{id}
    kind = task      -> id is a task event:   open /api/tasks/{task_id}
    """
    kind: Literal["guideline", "task"]
    id: int
    task_id: int | None
    name: str
    category: str
    coverage: str | None
    status: Status
    due_on: date
    days: int                    # negative = overdue by that many days
    last_done: date | None
    interval_months: int | None


class Counts(BaseModel):
    up_to_date: int
    due_soon: int
    overdue: int


class PopupOut(BaseModel):
    """A reminder waiting for Accept. item_* says what "Mark as done" acts on."""
    notification_id: int
    kind: str
    message: str
    created_at: datetime
    checkup_type_id: int | None
    task_event_id: int | None
    task_id: int | None
    prep_item_id: int | None
    prep_plan_id: int | None
    procedure_id: int | None


class HomeOut(BaseModel):
    """Everything the home screen needs in one request."""
    name: str
    counts: Counts
    popup: PopupOut | None             # the pop-up at the top
    next_item: ItemOut | None          # shown there when no reminder is waiting
    coming_up: list[ItemOut]           # late + upcoming, most urgent first
    plans: list["PrepPlanOut"]         # upcoming procedure preparations
    pending_reminders: int


class CalendarEntry(BaseModel):
    """One dot on the calendar."""
    date: date
    kind: Literal["guideline", "task", "log", "prep"]
    id: int                     # checkup type / task / log entry / procedure
    title: str
    category: str
    status: Literal["overdue", "due_soon", "up_to_date", "done", "missed", "planned"]


class LogEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    category: str
    done_on: date
    renew_on: date | None
    checkup_type_id: int | None
    task_id: int | None
    notes: str | None
    attachment_name: str | None
    created_at: datetime


class CheckupDetail(BaseModel):
    """GET /api/checkups/{id}: the guideline, its source, and your history."""
    item: ItemOut
    summary: str
    more_info: str | None
    preparation: str | None
    source_url: str | None
    procedure_id: int | None     # the matching preparation guide, if any
    history: list[LogEntryOut]


class MarkDone(BaseModel):
    done_on: date | None = None   # default: today
    notes: str | None = Field(default=None, max_length=2000)

    _check_date = field_validator("done_on")(_not_in_future)


class DoneOut(BaseModel):
    """After Mark as done: the log entry, plus what comes next for a repeating task."""
    entry: LogEntryOut | None
    next_due: date | None = None


# --------------------------------------------------------------------------
# tasks (the Add screen)
# --------------------------------------------------------------------------

class TaskCreate(BaseModel):
    """Body of POST /api/tasks.

    Repeating: first_date + repeat_every + repeat_unit.
    Manual:    first_date + any extra_dates, no repeat fields.
    """
    title: str = Field(min_length=1, max_length=80)
    category: Category = Field(max_length=40)
    first_date: date
    repeat_every: int | None = Field(default=None, ge=1, le=365)
    repeat_unit: RepeatUnit | None = None
    extra_dates: list[date] = Field(default=[], max_length=50)
    description: str | None = Field(default=None, max_length=2000)
    doctor_name: str | None = Field(default=None, max_length=80)
    doctor_specialty: str | None = Field(default=None, max_length=80)

    _category = field_validator("category")(_clean_category)

    @model_validator(mode="after")
    def repeat_is_complete(self):
        if (self.repeat_every is None) != (self.repeat_unit is None):
            raise ValueError("give both how often and the unit, or neither")
        if self.repeat_every is not None and self.extra_dates:
            raise ValueError("a repeating task cannot also have manual dates")
        return self


class TaskEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    due_on: date
    status: Literal["pending", "done", "missed"]
    done_on: date | None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    category: str
    description: str | None
    doctor_name: str | None
    doctor_specialty: str | None
    repeat_every: int | None
    repeat_unit: RepeatUnit | None
    created_at: datetime
    events: list[TaskEventOut]


class TaskDateAdd(BaseModel):
    due_on: date


# --------------------------------------------------------------------------
# log
# --------------------------------------------------------------------------

class LogEntryCreate(BaseModel):
    """Body of POST /api/log - "add your own": a one-off visit, test, vaccine...

    Send checkup_type_id to count it towards a recommended check.
    """
    title: str = Field(min_length=1, max_length=80)
    category: Category = Field(max_length=40)
    done_on: date
    renew_on: date | None = None
    checkup_type_id: int | None = None
    notes: str | None = Field(default=None, max_length=2000)

    _check_date = field_validator("done_on")(_not_in_future)
    _category = field_validator("category")(_clean_category)


class LogLine(BaseModel):
    """One line on the Log screen: something done, or a task occurrence missed."""
    kind: Literal["done", "missed"]
    id: int                     # log entry id (done) or task event id (missed)
    title: str
    category: str
    date: date
    notes: str | None = None
    attachment_name: str | None = None
    checkup_type_id: int | None = None
    task_id: int | None = None


class VaccinationOut(BaseModel):
    """One line of the vaccination passport."""
    name: str
    doses: list[date]            # newest first
    last_done: date | None
    renew_on: date | None        # None = no renewal known
    status: Status | None        # of the renewal; None = not recorded / no renewal
    checkup_type_id: int | None  # a recommended vaccine


# --------------------------------------------------------------------------
# procedures (Info) and preparation plans
# --------------------------------------------------------------------------

class ProcedureStepOut(BaseModel):
    id: int
    position: int
    text: str
    hours_before: int | None


class ProcedureListItem(BaseModel):
    id: int
    code: str
    name: str
    summary: str


class PrepPlanItemOut(BaseModel):
    id: int
    step_id: int
    text: str
    checked: bool
    remind_at: datetime | None
    sent_at: datetime | None


class PrepPlanOut(BaseModel):
    id: int
    procedure_id: int
    procedure_name: str
    appointment_at: datetime
    items: list[PrepPlanItemOut]


class ProcedureDetail(ProcedureListItem):
    steps: list[ProcedureStepOut]
    plans: list[PrepPlanOut]     # this user's upcoming plans for it


class PrepReminder(BaseModel):
    step_id: int
    remind_at: datetime | None = None   # default: appointment - hours_before


class PrepPlanCreate(BaseModel):
    """Body of POST /api/procedures/{id}/plans - "Set reminder".

    Every step goes on the checklist; only those in `reminders` get a reminder.
    """
    appointment_at: datetime
    reminders: list[PrepReminder] = []


class ItemChecked(BaseModel):
    checked: bool


# --------------------------------------------------------------------------
# notifications
# --------------------------------------------------------------------------

class NotificationItem(BaseModel):
    """One entry in the inbox."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    message: str
    checkup_type_id: int | None
    task_event_id: int | None
    prep_item_id: int | None
    accepted_at: datetime | None
    created_at: datetime


class Inbox(BaseModel):
    waiting: int                 # not accepted yet
    items: list[NotificationItem]


class ReminderRunOut(BaseModel):
    """What a reminder run did - returned by POST /api/notifications/check."""
    users_checked: int
    push: int
    sms: int
    prep: int
    dry_run: bool


class RecipientCount(BaseModel):
    """How many users can be texted at all - shown before you hit send."""
    recipients: int


class NotificationCreate(BaseModel):
    """Body of POST /api/notifications/send. The message, and nothing else:
    who receives it is decided by the phone numbers already in the database."""
    message: str = Field(min_length=1, max_length=1000)


class RecipientResult(BaseModel):
    """What happened for one recipient.

    status is one of: sent | dry_run | skipped | failed. A bad number for one
    person never stops the others, so every recipient gets a line.
    """
    user_id: int
    name: str
    phone: str | None
    status: str
    detail: str | None = None


class NotificationOut(BaseModel):
    """What POST /api/notifications/send returns."""
    dry_run: bool
    sent: int
    skipped: int
    failed: int
    results: list[RecipientResult]


HomeOut.model_rebuild()
