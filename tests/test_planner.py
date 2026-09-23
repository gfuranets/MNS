"""Tests for planner.py (who a guideline applies to, when things are due,
how repeating tasks move on), the daily reminder rule in reminders.py, and
the EN/LV texts in texts.py. Pure logic - no database needed.

Run from the project root:  venv/bin/python3 -m pytest
"""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from planner import (  # noqa: E402
    add_interval,
    add_months,
    age_on,
    guideline_items,
    interval_for,
    next_occurrence,
    sort_items,
    task_items,
)

TODAY = date(2026, 9, 22)


def checkup(id=1, name="Thing", **kw):
    """A CheckupType stand-in with no restrictions unless given."""
    base = dict(
        id=id, code=name.lower(), name=name, name_lv=None, category="checkup",
        coverage="state", interval_months=12,
        min_age=None, max_age=None, sex=None, country=None,
        risk_factor=None, risk_only=False, risk_interval_months=None, risk_min_age=None,
    )
    return SimpleNamespace(**{**base, **kw})


def user(birth_date=date(1994, 5, 1), sex="female", country="Latvia", risks=()):
    return SimpleNamespace(
        birth_date=birth_date, sex=sex, country=country, risk_codes=set(risks),
    )


CERVICAL = checkup(1, "Cervical screening", name_lv="Dzemdes kakla skrīnings",
                   interval_months=36, min_age=25, max_age=65, sex="female", country="Latvia")
CHOLESTEROL = checkup(2, "Cholesterol", interval_months=60, min_age=40,
                      risk_factor="heart", risk_interval_months=12, risk_min_age=20)
SKIN = checkup(3, "Skin check", risk_factor="cancer", risk_only=True)


class TestDates:
    def test_add_months(self):
        assert add_months(date(2026, 1, 15), 3) == date(2026, 4, 15)
        assert add_months(date(2025, 11, 1), 36) == date(2028, 11, 1)

    def test_add_months_clamps_month_end(self):
        assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
        assert add_months(date(2024, 2, 29), 12) == date(2025, 2, 28)

    @pytest.mark.parametrize("every,unit,expected", [
        (3, "day", date(2026, 9, 25)),
        (2, "week", date(2026, 10, 6)),
        (6, "month", date(2027, 3, 22)),
        (1, "year", date(2027, 9, 22)),
    ])
    def test_add_interval(self, every, unit, expected):
        assert add_interval(TODAY, every, unit) == expected

    def test_age_counts_the_birthday(self):
        assert age_on(date(2000, 9, 22), TODAY) == 26
        assert age_on(date(2000, 9, 23), TODAY) == 25

    def test_next_occurrence(self):
        assert next_occurrence(TODAY, 1, "month") == date(2026, 10, 22)
        assert next_occurrence(TODAY, None, None) is None


class TestWhoItAppliesTo:
    def test_matching_user(self):
        assert interval_for(CERVICAL, user(), set(), TODAY) == 36

    def test_wrong_sex(self):
        assert interval_for(CERVICAL, user(sex="male"), set(), TODAY) is None

    def test_other_sees_sex_specific_items(self):
        assert interval_for(CERVICAL, user(sex="other"), set(), TODAY) == 36

    def test_too_young_and_too_old(self):
        assert interval_for(CERVICAL, user(birth_date=date(2010, 1, 1)), set(), TODAY) is None
        assert interval_for(CERVICAL, user(birth_date=date(1950, 1, 1)), set(), TODAY) is None

    def test_age_limit_uses_the_exact_birthday(self):
        # turns 25 tomorrow -> not yet
        assert interval_for(CERVICAL, user(birth_date=date(2001, 9, 23)), set(), TODAY) is None
        assert interval_for(CERVICAL, user(birth_date=date(2001, 9, 22)), set(), TODAY) == 36

    def test_other_country(self):
        assert interval_for(CERVICAL, user(country="Estonia"), set(), TODAY) is None

    def test_country_is_case_insensitive(self):
        assert interval_for(CERVICAL, user(country=" latvia "), set(), TODAY) == 36

    def test_unknown_profile_leaves_it_out(self):
        assert interval_for(CERVICAL, user(birth_date=None), set(), TODAY) is None
        assert interval_for(CERVICAL, user(sex=None), set(), TODAY) is None

    def test_risk_factor_lowers_age_and_interval(self):
        u = user(birth_date=date(2000, 1, 1))                 # 26
        assert interval_for(CHOLESTEROL, u, set(), TODAY) is None
        assert interval_for(CHOLESTEROL, u, {"heart"}, TODAY) == 12

    def test_risk_only_item(self):
        assert interval_for(SKIN, user(), set(), TODAY) is None
        assert interval_for(SKIN, user(), {"cancer"}, TODAY) == 12


class TestGuidelineItems:
    def items(self, last_done=None, u=None, language="en"):
        u = u or user()
        return guideline_items(u, [CERVICAL, CHOLESTEROL, SKIN], last_done or {}, TODAY, language)

    def test_never_logged_is_due_today(self):
        [item] = self.items()
        assert (item.status, item.due_on, item.last_done) == ("due_soon", TODAY, None)

    def test_overdue(self):
        [item] = self.items({1: date(2023, 6, 1)})
        assert item.status == "overdue"
        assert item.due_on == date(2026, 6, 1)

    def test_due_soon(self):
        [item] = self.items({1: date(2023, 10, 4)})
        assert (item.status, item.days) == ("due_soon", 12)

    def test_up_to_date(self):
        [item] = self.items({1: date(2026, 1, 10)})
        assert item.status == "up_to_date"

    def test_latvian_name(self):
        [item] = self.items(language="lv")
        assert item.name == "Dzemdes kakla skrīnings"

    def test_sorted_most_urgent_first(self):
        u = user(birth_date=date(1980, 1, 1), risks={"cancer"})
        items = sort_items(self.items({1: date(2026, 1, 1), 2: date(2020, 1, 1)}, u=u))
        assert [i.status for i in items] == ["overdue", "due_soon", "up_to_date"]


class TestTaskItems:
    def event(self, id, due_on, task_id=7):
        task = SimpleNamespace(title="Physio", category="appointment")
        return SimpleNamespace(id=id, task_id=task_id, due_on=due_on, task=task)

    def test_statuses(self):
        items = task_items([
            self.event(1, TODAY - timedelta(days=2)),
            self.event(2, TODAY + timedelta(days=5)),
            self.event(3, TODAY + timedelta(days=90)),
        ], {7: date(2026, 9, 1)}, TODAY)
        assert [i.status for i in items] == ["overdue", "due_soon", "up_to_date"]
        assert items[0].key == ("task", 1)
        assert items[0].last_done == date(2026, 9, 1)
        assert items[0].name == "Physio"


# --------------------------------------------------------------------------
# reminder rule: daily until done
# --------------------------------------------------------------------------

from reminders import pick_due  # noqa: E402

NOW = datetime(2026, 9, 22, 10, 0)


def item(id, days, kind="guideline"):
    return SimpleNamespace(key=(kind, id), days=days)


class TestPickDue:
    def test_late_and_within_lead_time(self):
        items = [item(1, -10), item(2, 5), item(3, 8)]
        assert [i.key[1] for i in pick_due(items, 7, {}, NOW)] == [1, 2]

    def test_lead_time_zero_means_only_on_the_day(self):
        items = [item(1, 0), item(2, 1)]
        assert [i.key[1] for i in pick_due(items, 0, {}, NOW)] == [1]

    def test_once_a_day(self):
        earlier_today = {("guideline", 1): NOW - timedelta(hours=1)}
        assert pick_due([item(1, -10)], 7, earlier_today, NOW) == []

    def test_again_the_next_day(self):
        yesterday = {("guideline", 1): NOW - timedelta(days=1)}
        assert len(pick_due([item(1, -10)], 7, yesterday, NOW)) == 1

    def test_guideline_and_task_ids_do_not_collide(self):
        reminded = {("guideline", 1): NOW}
        assert len(pick_due([item(1, -1, kind="task")], 7, reminded, NOW)) == 1


# --------------------------------------------------------------------------
# texts: Latvian number agreement
# --------------------------------------------------------------------------

from texts import push_text, span, status_line  # noqa: E402


class TestSpan:
    @pytest.mark.parametrize("days,expected", [
        (1, "1 day"), (12, "12 days"), (21, "3 weeks"), (100, "3 months"), (800, "2 years"),
    ])
    def test_english(self, days, expected):
        assert span(days) == expected

    @pytest.mark.parametrize("days,case,expected", [
        (1, "gen", "1 dienas"),       # pēc 1 dienas
        (1, "acc", "1 dienu"),        # par 1 dienu
        (12, "gen", "12 dienām"),     # pēc 12 dienām
        (11, "gen", "11 dienām"),     # 11 is plural
        (35, "acc", "5 nedēļām"),
        (31, "acc", "4 nedēļām"),     # a month reads as weeks until day 60
        (100, "acc", "3 mēnešiem"),
        (800, "gen", "2 gadiem"),
    ])
    def test_latvian(self, days, case, expected):
        assert span(days, "lv", case) == expected

    def test_negative_days_read_the_same(self):
        assert span(-12, "lv") == span(12, "lv")


class TestMessages:
    def item(self, days, last_done=date(2023, 1, 1), kind="guideline"):
        return SimpleNamespace(name="Blood test", days=days, last_done=last_done, kind=kind)

    def test_status_lines(self):
        assert status_line(self.item(-100)) == "overdue by 3 months"
        assert status_line(self.item(-100), "lv") == "nokavēts par 3 mēnešiem"
        assert status_line(self.item(12), "lv") == "pēc 12 dienām"
        assert status_line(self.item(0)) == "due today"
        assert status_line(self.item(0, last_done=None)) == "no record yet"

    def test_push_texts(self):
        assert push_text(self.item(12)) == "Blood test is due in 12 days."
        assert push_text(self.item(12), "lv") == "Blood test: termiņš pēc 12 dienām."
        assert "was due 2 days ago" in push_text(self.item(-2, kind="task"))
