"""models.py - SQLAlchemy tables. These mirror query.sql exactly."""
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

# Kept as plain tuples so schema.py can build its Literal types from the same
# values - one list per ENUM, shared by the database and the API.
SEXES = ("female", "male", "other")
RISK_CODES = ("cancer", "diabetes", "heart", "other")
RISK_SCOPES = ("personal", "family")
LANGUAGES = ("en", "lv")
CATEGORIES = ("screening", "vaccination", "checkup")
COVERAGES = ("state", "private")
REPEAT_UNITS = ("day", "week", "month", "year")
EVENT_STATUSES = ("pending", "done", "missed")
CHANNELS = ("push", "sms")
NOTIFICATION_KINDS = ("overdue", "due_soon", "prep", "broadcast")
NOTIFICATION_STATUSES = ("delivered", "sent", "dry_run", "skipped", "failed")


def localized(row, field: str, language: str) -> str | None:
    """row.<field>_lv for Latvian users when it exists, else the English text."""
    if language == "lv":
        value = getattr(row, f"{field}_lv", None)
        if value:
            return value
    return getattr(row, field)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # login credentials
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(60), nullable=False)

    name: Mapped[str] = mapped_column(String(40), nullable=False)
    surname: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # profile - onboarding step 3. NULL until the user fills it in, and the
    # schedule simply leaves out whatever guideline it cannot evaluate yet.
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    sex: Mapped[str | None] = mapped_column(Enum(*SEXES), nullable=True)
    country: Mapped[str | None] = mapped_column(String(40), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # settings
    language: Mapped[str] = mapped_column(Enum(*LANGUAGES), nullable=False, default="en")
    reminders_on: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reminder_lead_days: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=7)
    remind_push: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    remind_sms: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # onboarding step 2
    consent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    risk_factors: Mapped[list["RiskFactor"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def profile_complete(self) -> bool:
        """True once consent is given and the three planning fields are set."""
        return None not in (self.consent_at, self.birth_date, self.sex, self.country)

    @property
    def risk_codes(self) -> set[str]:
        """Conditions that raise risk, whether personal or in the family -
        the guidelines treat both the same way."""
        return {r.code for r in self.risk_factors}

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"


class RiskFactor(Base):
    """One ticked box on the profile page. `note` holds the free text of "Other"."""
    __tablename__ = "risk_factors"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    code: Mapped[str] = mapped_column(Enum(*RISK_CODES), primary_key=True)
    scope: Mapped[str] = mapped_column(Enum(*RISK_SCOPES), primary_key=True)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)


class CheckupType(Base):
    """A guideline: what to do, how often, and who it applies to.

    Rows are seeded by query.sql - users never write to this table.
    """
    __tablename__ = "checkup_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    name_lv: Mapped[str | None] = mapped_column(String(80), nullable=True)
    category: Mapped[str] = mapped_column(Enum(*CATEGORIES), nullable=False)
    coverage: Mapped[str] = mapped_column(Enum(*COVERAGES), nullable=False)

    # who it applies to. NULL means "no restriction".
    interval_months: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    min_age: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    max_age: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    sex: Mapped[str | None] = mapped_column(Enum("female", "male"), nullable=True)
    country: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # risk factors: either the item exists only for people with the factor
    # (risk_only), or they get it earlier / more often (risk_* overrides).
    risk_factor: Mapped[str | None] = mapped_column(
        Enum("cancer", "diabetes", "heart"), nullable=True
    )
    risk_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    risk_interval_months: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    risk_min_age: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    # item detail page
    summary: Mapped[str] = mapped_column(String(300), nullable=False)
    summary_lv: Mapped[str | None] = mapped_column(String(300), nullable=True)
    more_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    preparation: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    procedure_code: Mapped[str | None] = mapped_column(String(40), nullable=True)

    def __repr__(self) -> str:
        return f"<CheckupType {self.code}>"


class Task(Base):
    """Something the user added themselves on the Add screen.

    repeat_every/repeat_unit set = repeats; both NULL = manual dates only.
    """
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(80), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    doctor_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    doctor_specialty: Mapped[str | None] = mapped_column(String(80), nullable=True)
    repeat_every: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    repeat_unit: Mapped[str | None] = mapped_column(Enum(*REPEAT_UNITS), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    events: Mapped[list["TaskEvent"]] = relationship(
        back_populates="task", cascade="all, delete-orphan",
        order_by="TaskEvent.due_on", lazy="selectin",
    )

    @property
    def repeats(self) -> bool:
        return self.repeat_every is not None and self.repeat_unit is not None


class TaskEvent(Base):
    """One dated occurrence of a task: pending, done or missed."""
    __tablename__ = "task_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    due_on: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(Enum(*EVENT_STATUSES), nullable=False, default="pending")
    done_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    task: Mapped[Task] = relationship(back_populates="events", lazy="joined")


class LogEntry(Base):
    """Something the user did. done_on may be in the past - backdating is normal."""
    __tablename__ = "log_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # At most one of these is set: a recommended check, or one of the user's
    # own tasks. Neither = a one-off "add your own" entry.
    checkup_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("checkup_types.id", ondelete="SET NULL"), nullable=True
    )
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(80), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    done_on: Mapped[date] = mapped_column(Date, nullable=False)
    renew_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # optional photo/PDF. The file lives in app/uploads/<attachment_path>.
    attachment_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attachment_path: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    checkup_type: Mapped[CheckupType | None] = relationship(lazy="joined")
    task: Mapped[Task | None] = relationship(lazy="joined")


class Procedure(Base):
    """A preparation guide in the Info library. Seeded by query.sql."""
    __tablename__ = "procedures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    name_lv: Mapped[str | None] = mapped_column(String(80), nullable=True)
    keywords: Mapped[str | None] = mapped_column(String(255), nullable=True)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    summary_lv: Mapped[str | None] = mapped_column(String(500), nullable=True)

    steps: Mapped[list["ProcedureStep"]] = relationship(
        order_by="ProcedureStep.position", lazy="selectin"
    )


class ProcedureStep(Base):
    """One checklist line. hours_before = when a reminder for it makes sense."""
    __tablename__ = "procedure_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    procedure_id: Mapped[int] = mapped_column(
        ForeignKey("procedures.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    text: Mapped[str] = mapped_column(String(255), nullable=False)
    text_lv: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hours_before: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)


class PrepPlan(Base):
    """"Set reminder" on a procedure: the appointment time plus a checklist."""
    __tablename__ = "prep_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    procedure_id: Mapped[int] = mapped_column(
        ForeignKey("procedures.id", ondelete="CASCADE"), nullable=False
    )
    appointment_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    procedure: Mapped[Procedure] = relationship(lazy="joined")
    items: Mapped[list["PrepPlanItem"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", lazy="selectin"
    )


class PrepPlanItem(Base):
    """One checklist line of a plan: ticked or not, and when to remind."""
    __tablename__ = "prep_plan_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("prep_plans.id", ondelete="CASCADE"), nullable=False
    )
    step_id: Mapped[int] = mapped_column(
        ForeignKey("procedure_steps.id", ondelete="CASCADE"), nullable=False
    )
    checked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    remind_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    plan: Mapped[PrepPlan] = relationship(back_populates="items", lazy="joined")
    step: Mapped[ProcedureStep] = relationship(lazy="joined")


class Notification(Base):
    """Every reminder or broadcast, on every channel.

    channel = push rows are the in-app inbox and the pop-ups: accepted_at
    stays NULL until the user presses Accept. The table is also what the
    reminder loop reads to send at most one reminder per item a day.
    """
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # What the reminder is about - at most one is set (none for a broadcast).
    checkup_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("checkup_types.id", ondelete="SET NULL"), nullable=True
    )
    task_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("task_events.id", ondelete="CASCADE"), nullable=True
    )
    prep_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("prep_plan_items.id", ondelete="CASCADE"), nullable=True
    )
    channel: Mapped[str] = mapped_column(Enum(*CHANNELS), nullable=False)
    kind: Mapped[str] = mapped_column(Enum(*NOTIFICATION_KINDS), nullable=False)
    message: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(Enum(*NOTIFICATION_STATUSES), nullable=False)
    detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
