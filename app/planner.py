"""planner.py - turns a profile and a log into "what is due when".

Pure functions only: no database, no HTTP. crud.py loads the rows and hands
them in; the home page, the schedule, the item detail page and the reminder
loop all read the same answer from here, so they can never disagree.

The rules:

  * A guideline applies if the user's age, sex, country and risk factors fit it.
    Anything the profile does not say yet (e.g. no birth year) leaves out the
    guidelines that depend on it rather than guessing.
  * due_on = last time it was done + the interval. Never logged = due today:
    we do not know it was ever done, but calling a brand-new user "overdue" on
    everything would be alarming and probably wrong.
  * overdue   - due_on is in the past
    due_soon  - due within DUE_SOON_DAYS
    up_to_date - otherwise
"""
import calendar
from dataclasses import dataclass
from datetime import date

DUE_SOON_DAYS = 30

# Order used everywhere a list is shown: most urgent first.
STATUS_ORDER = {"overdue": 0, "due_soon": 1, "up_to_date": 2}


@dataclass
class ScheduleItem:
    checkup: object              # models.CheckupType (kept loose so tests can use stand-ins)
    status: str                  # overdue | due_soon | up_to_date
    interval_months: int         # after risk-factor adjustment
    last_done: date | None
    due_on: date
    days: int                    # due_on - today: negative = overdue by, positive = due in
    snoozed_until: date | None   # "remind me later" still in effect

    @property
    def snoozed(self) -> bool:
        return self.snoozed_until is not None


def add_months(d: date, months: int) -> date:
    """date + N calendar months, clamping the day (Jan 31 + 1 month = Feb 28/29)."""
    month_index = d.month - 1 + months
    year, month = d.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def age_in(birth_year: int, today: date) -> int:
    """Age this calendar year. We only store the year, so this can be one too
    high before the birthday - close enough for "ages 25-65" guidelines."""
    return today.year - birth_year


def _same_country(a: str | None, b: str | None) -> bool:
    return (a or "").strip().casefold() == (b or "").strip().casefold()


def interval_for(checkup, user, risks: set[str], today: date) -> int | None:
    """The interval in months if this guideline applies to the user, else None."""
    has_risk = checkup.risk_factor is not None and checkup.risk_factor in risks

    if checkup.risk_only and not has_risk:
        return None

    if checkup.country is not None:
        if user.country is None or not _same_country(checkup.country, user.country):
            return None

    # "other" sees both sex-specific lists: a fixed male/female split would
    # silently drop screenings some people need.
    if checkup.sex is not None:
        if user.sex is None or (user.sex != "other" and user.sex != checkup.sex):
            return None

    min_age = checkup.min_age
    if has_risk and checkup.risk_min_age is not None:
        min_age = checkup.risk_min_age

    if min_age is not None or checkup.max_age is not None:
        if user.birth_year is None:
            return None
        age = age_in(user.birth_year, today)
        if min_age is not None and age < min_age:
            return None
        if checkup.max_age is not None and age > checkup.max_age:
            return None

    if has_risk and checkup.risk_interval_months is not None:
        return checkup.risk_interval_months
    return checkup.interval_months


def status_for(due_on: date, today: date) -> str:
    days = (due_on - today).days
    if days < 0:
        return "overdue"
    if days <= DUE_SOON_DAYS:
        return "due_soon"
    return "up_to_date"


def build_schedule(
    user,
    checkups: list,
    last_done: dict[int, date],
    snoozes: dict[int, date],
    today: date,
) -> list[ScheduleItem]:
    """Every guideline that applies to `user`, most urgent first.

    last_done - checkup_type_id -> most recent done_on from the log
    snoozes   - checkup_type_id -> "remind me later" date (expired ones ignored)
    """
    risks = user.risk_codes
    items = []

    for checkup in checkups:
        interval = interval_for(checkup, user, risks, today)
        if interval is None:
            continue

        done = last_done.get(checkup.id)
        due_on = add_months(done, interval) if done else today
        snooze = snoozes.get(checkup.id)

        items.append(ScheduleItem(
            checkup=checkup,
            status=status_for(due_on, today),
            interval_months=interval,
            last_done=done,
            due_on=due_on,
            days=(due_on - today).days,
            snoozed_until=snooze if snooze and snooze > today else None,
        ))

    items.sort(key=lambda i: (STATUS_ORDER[i.status], i.due_on, i.checkup.name))
    return items


def describe(item: ScheduleItem) -> str:
    """The one-line status under an item's name: "due in 12 days" and so on."""
    if item.last_done is None:
        return "no record yet"
    if item.status == "overdue":
        return f"overdue by {_span(-item.days)}"
    if item.days == 0:
        return "due today"
    if item.status == "due_soon":
        return f"due in {_span(item.days)}"
    return f"next due {item.due_on:%b %Y}"


def _span(days: int) -> str:
    """12 days / 3 weeks / 4 months / 2 years - whichever reads naturally."""
    if days < 14:
        return f"{days} day{'s' if days != 1 else ''}"
    if days < 60:
        return f"{days // 7} weeks"
    if days < 730:
        return f"{days // 30} months"
    return f"{days // 365} years"
