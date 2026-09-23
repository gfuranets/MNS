"""Tests for planner.py (who a guideline applies to, and when it is due) and
for the reminder rules in reminders.py. Pure logic - no database needed.

Run from the project root:  venv/bin/python3 -m pytest
"""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from planner import add_months, build_schedule, describe, interval_for  # noqa: E402

TODAY = date(2026, 9, 22)


def checkup(id=1, name="Thing", **kw):
    """A CheckupType stand-in with no restrictions unless given."""
    base = dict(
        id=id, code=name.lower(), name=name, interval_months=12,
        min_age=None, max_age=None, sex=None, country=None,
        risk_factor=None, risk_only=False, risk_interval_months=None, risk_min_age=None,
    )
    return SimpleNamespace(**{**base, **kw})


def user(birth_year=1994, sex="female", country="Latvia", risks=()):
    return SimpleNamespace(
        birth_year=birth_year, sex=sex, country=country, risk_codes=set(risks),
    )


CERVICAL = checkup(1, "Cervical screening", interval_months=36,
                   min_age=25, max_age=65, sex="female", country="Latvia")
CHOLESTEROL = checkup(2, "Cholesterol", interval_months=60, min_age=40,
                      risk_factor="family_heart", risk_interval_months=12, risk_min_age=20)
SKIN = checkup(3, "Skin check", risk_factor="family_cancer", risk_only=True)


class TestAddMonths:
    def test_simple(self):
        assert add_months(date(2026, 1, 15), 3) == date(2026, 4, 15)

    def test_crosses_year(self):
        assert add_months(date(2025, 11, 1), 36) == date(2028, 11, 1)

    def test_clamps_month_end(self):
        assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)

    def test_leap_day(self):
        assert add_months(date(2024, 2, 29), 12) == date(2025, 2, 28)


class TestWhoItAppliesTo:
    def test_matching_user(self):
        assert interval_for(CERVICAL, user(), set(), TODAY) == 36

    def test_wrong_sex(self):
        assert interval_for(CERVICAL, user(sex="male"), set(), TODAY) is None

    def test_other_sees_sex_specific_items(self):
        assert interval_for(CERVICAL, user(sex="other"), set(), TODAY) == 36

    def test_too_young_and_too_old(self):
        assert interval_for(CERVICAL, user(birth_year=2010), set(), TODAY) is None
        assert interval_for(CERVICAL, user(birth_year=1950), set(), TODAY) is None

    def test_other_country(self):
        assert interval_for(CERVICAL, user(country="Estonia"), set(), TODAY) is None

    def test_country_is_case_insensitive(self):
        assert interval_for(CERVICAL, user(country=" latvia "), set(), TODAY) == 36

    def test_unknown_profile_leaves_it_out(self):
        assert interval_for(CERVICAL, user(birth_year=None), set(), TODAY) is None
        assert interval_for(CERVICAL, user(sex=None), set(), TODAY) is None

    def test_risk_factor_lowers_age_and_interval(self):
        u = user(birth_year=2000)                      # 26
        assert interval_for(CHOLESTEROL, u, set(), TODAY) is None
        assert interval_for(CHOLESTEROL, u, {"family_heart"}, TODAY) == 12

    def test_risk_only_item(self):
        assert interval_for(SKIN, user(), set(), TODAY) is None
        assert interval_for(SKIN, user(), {"family_cancer"}, TODAY) == 12


class TestSchedule:
    def schedule(self, last_done=None, snoozes=None, u=None):
        return build_schedule(
            u or user(), [CERVICAL, CHOLESTEROL, SKIN],
            last_done or {}, snoozes or {}, TODAY,
        )

    def test_never_logged_is_due_today(self):
        [item] = self.schedule()
        assert item.status == "due_soon"
        assert item.due_on == TODAY
        assert describe(item) == "no record yet"

    def test_overdue(self):
        [item] = self.schedule({1: date(2023, 6, 1)})
        assert item.status == "overdue"
        assert item.due_on == date(2026, 6, 1)
        assert describe(item) == "overdue by 3 months"

    def test_due_soon(self):
        [item] = self.schedule({1: date(2023, 10, 4)})
        assert item.status == "due_soon"
        assert describe(item) == "due in 12 days"

    def test_up_to_date(self):
        [item] = self.schedule({1: date(2026, 1, 10)})
        assert item.status == "up_to_date"

    def test_sorted_most_urgent_first(self):
        u = user(birth_year=1980, risks={"family_cancer"})
        items = self.schedule({1: date(2026, 1, 1), 2: date(2020, 1, 1)}, u=u)
        assert [i.status for i in items] == ["overdue", "due_soon", "up_to_date"]

    def test_expired_snooze_is_ignored(self):
        [item] = self.schedule(snoozes={1: TODAY - timedelta(days=1)})
        assert item.snoozed_until is None

    def test_active_snooze(self):
        [item] = self.schedule(snoozes={1: TODAY + timedelta(days=5)})
        assert item.snoozed


# --------------------------------------------------------------------------
# reminder rules
# --------------------------------------------------------------------------

from reminders import pick_due  # noqa: E402

NOW = datetime(2026, 9, 22, 12, 0)


def item(id, days, snoozed=False):
    return SimpleNamespace(
        checkup=SimpleNamespace(id=id), days=days, snoozed=snoozed,
    )


class TestPickDue:
    def test_off_sends_nothing(self):
        assert pick_due([item(1, -10)], "off", {}, NOW) == []

    def test_gentle_only_near_items(self):
        items = [item(1, -10), item(2, 5), item(3, 20)]
        assert [i.checkup.id for i in pick_due(items, "gentle", {}, NOW)] == [1, 2]

    def test_frequent_whole_due_soon_window(self):
        items = [item(1, -10), item(2, 5), item(3, 20), item(4, 90)]
        assert [i.checkup.id for i in pick_due(items, "frequent", {}, NOW)] == [1, 2, 3]

    def test_snoozed_items_are_skipped(self):
        assert pick_due([item(1, -10, snoozed=True)], "frequent", {}, NOW) == []

    @pytest.mark.parametrize("style,days_ago,expected", [
        ("gentle", 10, False), ("gentle", 31, True),
        ("frequent", 3, False), ("frequent", 8, True),
    ])
    def test_cooldown(self, style, days_ago, expected):
        reminded = {1: NOW - timedelta(days=days_ago)}
        assert bool(pick_due([item(1, -10)], style, reminded, NOW)) is expected
