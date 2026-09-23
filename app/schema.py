"""schema.py - Pydantic models: the shape of data going in and out of the API.

Keep these separate from models.py. models.py describes the database;
schema.py describes the JSON contract. UserOut has no password_hash field,
so a hash can never leak out through a response even by accident.
"""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Sex = Literal["female", "male", "other"]
RiskCode = Literal["family_cancer", "family_diabetes", "family_heart", "other"]
ReminderStyle = Literal["off", "gentle", "frequent"]
Language = Literal["en", "lv", "ru"]
Status = Literal["overdue", "due_soon", "up_to_date"]


# --------------------------------------------------------------------------
# users
# --------------------------------------------------------------------------

class UserCreate(BaseModel):
    """Body of POST /api/signup. Just enough to log in - the health profile
    comes on the next screen (PUT /api/me/profile)."""
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)  # bcrypt caps at 72 bytes
    name: str = Field(min_length=1, max_length=40)
    phone: str | None = Field(default=None, max_length=20)


class UserLogin(BaseModel):
    """Body of POST /api/login."""
    email: EmailStr
    password: str


class RiskFactorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: RiskCode
    note: str | None


class UserOut(BaseModel):
    """What the API returns about a user. Deliberately has no password field."""
    model_config = ConfigDict(from_attributes=True)  # lets us build it from a User row

    id: int
    email: EmailStr
    name: str
    birth_year: int | None
    sex: Sex | None
    country: str | None
    phone: str | None
    risk_factors: list[RiskFactorOut]
    profile_complete: bool          # False -> the frontend shows onboarding
    language: Language
    reminder_style: ReminderStyle
    remind_push: bool
    remind_sms: bool
    created_at: datetime


class ProfileUpdate(BaseModel):
    """Body of PUT /api/me/profile - onboarding step 2.

    Birth year, sex and country are required. Risk factors are optional and
    replace whatever was saved before; risk_other is the "Other: ..." text.
    """
    birth_year: int = Field(ge=1900)
    sex: Sex
    country: str = Field(min_length=1, max_length=40)
    risk_factors: list[RiskCode] = []
    risk_other: str | None = Field(default=None, max_length=200)

    @field_validator("birth_year")
    @classmethod
    def not_in_future(cls, year: int) -> int:
        if year > date.today().year:
            raise ValueError("birth year cannot be in the future")
        return year


class SettingsUpdate(BaseModel):
    """Body of PATCH /api/me/settings. Every field is optional: send only what changed."""
    language: Language | None = None
    reminder_style: ReminderStyle | None = None
    remind_push: bool | None = None
    remind_sms: bool | None = None
    phone: str | None = Field(default=None, max_length=20)


class Token(BaseModel):
    """What POST /api/login returns."""
    access_token: str
    token_type: str = "bearer"


# --------------------------------------------------------------------------
# schedule
# --------------------------------------------------------------------------

class ScheduleItemOut(BaseModel):
    """One row of the schedule, and the header of the item detail page."""
    id: int                      # checkup_type id - use it for /api/checkups/{id}
    code: str
    name: str
    category: str
    coverage: str
    status: Status
    status_text: str             # "due in 12 days", "overdue by 3 months", ...
    interval_months: int
    last_done: date | None
    due_on: date
    days: int                    # negative = overdue by that many days
    snoozed_until: date | None


class CheckupDetail(ScheduleItemOut):
    """GET /api/checkups/{id}: the schedule row plus the explanatory texts."""
    summary: str
    more_info: str | None        # "Show more info"
    preparation: str | None      # "See preparation guide"
    source_url: str | None       # "View guideline source"
    history: list["LogEntryOut"]


class Counts(BaseModel):
    up_to_date: int
    due_soon: int
    overdue: int


class HomeOut(BaseModel):
    """Everything the home screen needs in one request."""
    name: str
    profile_complete: bool
    counts: Counts
    urgent: ScheduleItemOut | None     # the red card: most overdue, not snoozed
    coming_up: list[ScheduleItemOut]   # due soon
    unread_notifications: int


class CheckupTypeOut(BaseModel):
    """The catalog - for the "What did you do?" picker on the log form."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    category: str


class SnoozeCreate(BaseModel):
    days: int = Field(default=30, ge=1, le=365)


def _not_in_future(d: date | None) -> date | None:
    if d is not None and d > date.today():
        raise ValueError("cannot log something that has not happened yet")
    return d


class MarkDone(BaseModel):
    done_on: date | None = None   # default: today
    notes: str | None = Field(default=None, max_length=2000)

    _check_date = field_validator("done_on")(_not_in_future)


class PrepGuide(BaseModel):
    id: int
    name: str
    status: Status
    status_text: str
    preparation: str


class VaccinationOut(BaseModel):
    """One line of the vaccination passport."""
    id: int
    name: str
    last_done: date | None
    due_on: date
    status: Status
    doses: list[date]            # every logged dose, newest first


# --------------------------------------------------------------------------
# log
# --------------------------------------------------------------------------

class LogEntryCreate(BaseModel):
    """Body of POST /api/log.

    Send checkup_type_id when the user picked from the list. Otherwise the
    title is matched against the catalog by name, and a title that matches
    nothing is still saved - it just does not move any due date.
    """
    title: str = Field(min_length=1, max_length=80)
    done_on: date
    checkup_type_id: int | None = None
    notes: str | None = Field(default=None, max_length=2000)

    _check_date = field_validator("done_on")(_not_in_future)


class LogEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    done_on: date
    checkup_type_id: int | None
    notes: str | None
    attachment_name: str | None
    created_at: datetime


# --------------------------------------------------------------------------
# notifications
# --------------------------------------------------------------------------

class NotificationItem(BaseModel):
    """One entry in the in-app inbox."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    checkup_type_id: int | None
    kind: str
    message: str
    read_at: datetime | None
    created_at: datetime


class Inbox(BaseModel):
    unread: int
    items: list[NotificationItem]


class ReminderRunOut(BaseModel):
    """What a reminder run did - returned by POST /api/notifications/check."""
    users_checked: int
    push: int
    sms: int
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


CheckupDetail.model_rebuild()
