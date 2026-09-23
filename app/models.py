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
RISK_CODES = ("family_cancer", "family_diabetes", "family_heart", "other")
REMINDER_STYLES = ("off", "gentle", "frequent")
LANGUAGES = ("en", "lv", "ru")
CATEGORIES = ("screening", "vaccination", "checkup")
COVERAGES = ("state", "private")
CHANNELS = ("push", "sms")
NOTIFICATION_KINDS = ("overdue", "due_soon", "broadcast")
NOTIFICATION_STATUSES = ("delivered", "sent", "dry_run", "skipped", "failed")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # login credentials
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(60), nullable=False)

    name: Mapped[str] = mapped_column(String(40), nullable=False)

    # profile - onboarding step 2. NULL until the user fills it in, and the
    # schedule simply leaves out whatever guideline it cannot evaluate yet.
    birth_year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    sex: Mapped[str | None] = mapped_column(Enum(*SEXES), nullable=True)
    country: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # for SMS reminders; optional
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # settings
    language: Mapped[str] = mapped_column(Enum(*LANGUAGES), nullable=False, default="en")
    reminder_style: Mapped[str] = mapped_column(
        Enum(*REMINDER_STYLES), nullable=False, default="gentle"
    )
    remind_push: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    remind_sms: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    risk_factors: Mapped[list["RiskFactor"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def profile_complete(self) -> bool:
        return None not in (self.birth_year, self.sex, self.country)

    @property
    def risk_codes(self) -> set[str]:
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
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)


class CheckupType(Base):
    """A guideline: what to do, how often, and who it applies to.

    Rows are seeded by query.sql - users never write to this table.
    """
    __tablename__ = "checkup_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
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
    risk_factor: Mapped[str | None] = mapped_column(Enum(*RISK_CODES), nullable=True)
    risk_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    risk_interval_months: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    risk_min_age: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    # item detail page
    summary: Mapped[str] = mapped_column(String(300), nullable=False)
    more_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    preparation: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        return f"<CheckupType {self.code}>"


class LogEntry(Base):
    """Something the user did. done_on may be in the past - backdating is normal."""
    __tablename__ = "log_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # NULL when the title did not match any guideline - still worth keeping.
    checkup_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("checkup_types.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(80), nullable=False)
    done_on: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # optional photo/PDF. The file lives in app/uploads/<attachment_path>.
    attachment_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attachment_path: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    checkup_type: Mapped[CheckupType | None] = relationship(lazy="joined")


class Snooze(Base):
    """"Remind me later": no reminders for this item until `until`."""
    __tablename__ = "snoozes"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    checkup_type_id: Mapped[int] = mapped_column(
        ForeignKey("checkup_types.id", ondelete="CASCADE"), primary_key=True
    )
    until: Mapped[date] = mapped_column(Date, nullable=False)


class Notification(Base):
    """Every reminder or broadcast, on every channel.

    Doubles as the in-app inbox (channel = push) and as the memory the reminder
    loop checks so it does not nag about the same item twice in a row.
    """
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    checkup_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("checkup_types.id", ondelete="SET NULL"), nullable=True
    )
    channel: Mapped[str] = mapped_column(Enum(*CHANNELS), nullable=False)
    kind: Mapped[str] = mapped_column(Enum(*NOTIFICATION_KINDS), nullable=False)
    message: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(Enum(*NOTIFICATION_STATUSES), nullable=False)
    detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
