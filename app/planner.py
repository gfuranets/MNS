"""planner.py - turns a profile, a log and the user's own tasks into
"what is due when".

Pure functions only: no database, no HTTP. crud.py loads the rows and hands
them in; the home page, the schedule, the calendar and the reminder loop all
read the same answer from here, so they can never disagree.

Two kinds of item end up in one list:

  guideline - a recommended check from the catalog. It applies if the user's
              age, sex, country and risk factors fit. due_on = last time it
              was logged + the interval; never logged = due today (we do not
              know it was ever done, but calling everything "overdue" on day
              one would be alarming and probably wrong).
  task      - a pending occurrence of something the user added themselves.
              due_on is simply the date they gave.

  overdue    - due_on is in the past            (shown as "late")
  due_soon   - due within DUE_SOON_DAYS          (shown as "upcoming")
  up_to_date - otherwise
"""
import calendar
from dataclasses import dataclass
from datetime import date, timedelta

DUE_SOON_DAYS = 30

# Order used everywhere a list is shown: most urgent first.
STATUS_ORDER = {"overdue": 0, "due_soon": 1, "up_to_date": 2}


@dataclass
class Item:
    kind: str                    # guideline | task
    id: int                      # checkup_type id, or task_event id
    name: str
    category: str
    status: str                  # overdue | due_soon | up_to_date
    due_on: date
    days: int                    # due_on - today: negative = overdue by
    last_done: date | None
    interval_months: int | None = None   # guideline, after risk adjustment
    task_id: int | None = None
    coverage: str | None = None
    remind_every_minutes: int | None = None   # task only: repeat the email
    source: object = None        # the CheckupType or TaskEvent it came from

    @property
    def key(self) -> tuple[str, int]:
        return (self.kind, self.id)


# --------------------------------------------------------------------------
# dates
# --------------------------------------------------------------------------

def add_months(d: date, months: int) -> date:
    """date + N calendar months, clamping the day (Jan 31 + 1 month = Feb 28/29)."""
    month_index = d.month - 1 + months
    year, month = d.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def add_interval(d: date, every: int, unit: str) -> date:
    """date + "every 2 weeks" and the like - the repeat rule of a task."""
    if unit == "day":
        return d + timedelta(days=every)
    if unit == "week":
        return d + timedelta(weeks=every)
    if unit == "month":
        return add_months(d, every)
    if unit == "year":
        return add_months(d, 12 * every)
    raise ValueError(f"unknown repeat unit {unit!r}")


def age_on(birth_date: date, today: date) -> int:
    """Whole years, counting the birthday itself."""
    before_birthday = (today.month, today.day) < (birth_date.month, birth_date.day)
    return today.year - birth_date.year - before_birthday


def status_for(due_on: date, today: date) -> str:
    days = (due_on - today).days
    if days < 0:
        return "overdue"
    if days <= DUE_SOON_DAYS:
        return "due_soon"
    return "up_to_date"


# --------------------------------------------------------------------------
# guidelines
# --------------------------------------------------------------------------

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
        if user.birth_date is None:
            return None
        age = age_on(user.birth_date, today)
        if min_age is not None and age < min_age:
            return None
        if checkup.max_age is not None and age > checkup.max_age:
            return None

    if has_risk and checkup.risk_interval_months is not None:
        return checkup.risk_interval_months
    return checkup.interval_months


def guideline_items(
    user, checkups: list, last_done: dict[int, date], today: date, language: str = "en",
) -> list[Item]:
    """Every recommended check that applies to `user`.

    last_done - checkup_type_id -> most recent done_on from the log
    """
    risks = user.risk_codes
    items = []

    for checkup in checkups:
        interval = interval_for(checkup, user, risks, today)
        if interval is None:
            continue

        done = last_done.get(checkup.id)
        due_on = add_months(done, interval) if done else today
        name = (getattr(checkup, "name_lv", None) if language == "lv" else None) or checkup.name

        items.append(Item(
            kind="guideline", id=checkup.id, name=name, category=checkup.category,
            status=status_for(due_on, today), due_on=due_on,
            days=(due_on - today).days, last_done=done,
            interval_months=interval, coverage=checkup.coverage, source=checkup,
        ))
    return items


# --------------------------------------------------------------------------
# the user's own tasks
# --------------------------------------------------------------------------

def task_items(pending_events: list, last_done: dict[int, date], today: date) -> list[Item]:
    """One item per pending task occurrence.

    last_done - task_id -> most recent done_on of that task
    """
    return [
        Item(
            kind="task", id=e.id, name=e.task.title, category=e.task.category,
            status=status_for(e.due_on, today), due_on=e.due_on,
            days=(e.due_on - today).days, last_done=last_done.get(e.task_id),
            task_id=e.task_id, remind_every_minutes=e.task.remind_every_minutes, source=e,
        )
        for e in pending_events
    ]


def sort_items(items: list[Item]) -> list[Item]:
    return sorted(items, key=lambda i: (STATUS_ORDER[i.status], i.due_on, i.name))


def next_occurrence(due_on: date, every: int | None, unit: str | None) -> date | None:
    """The date after `due_on` for a repeating task, or None for manual dates."""
    if every is None or unit is None:
        return None
    return add_interval(due_on, every, unit)


# --------------------------------------------------------------------------
# lab results
# --------------------------------------------------------------------------

def lab_flag(value: float, comparator: str | None, low: float | None, high: float | None) -> str:
    """low | normal | high against the range the lab printed. A result the
    lab could only give as "< 1.0" is never low, and "> 90" never high."""
    if low is not None and value < low and comparator != ">":
        return "low"
    if high is not None and value > high and comparator != "<":
        return "high"
    return "normal"

