"""Tests for phone normalization - the one piece of real logic in the
notifications feature. Everything else is a database read or an HTTP call.

Run from the project root:  venv/bin/python3 -m pytest
"""
import sys
from pathlib import Path

import pytest

# The app modules import each other flatly (`import crud`), so app/ has to be
# importable as a top-level directory - same reason uvicorn is run from inside it.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from notifications import dial_code, normalize_phone  # noqa: E402


class TestAlreadyInternational:
    """A number that carries its own prefix is trusted over the country column."""

    def test_plain_e164_passes_through(self):
        assert normalize_phone("+37120123456", "Latvia") == "+37120123456"

    def test_separators_are_stripped(self):
        assert normalize_phone("+371 20-123 456", "Latvia") == "+37120123456"

    def test_brackets_and_dots(self):
        assert normalize_phone("+1 (555) 010.9999", "United States") == "+15550109999"

    def test_double_zero_is_treated_as_plus(self):
        assert normalize_phone("0037120123456", "Latvia") == "+37120123456"

    def test_prefix_wins_over_a_mismatched_country(self):
        # Someone with a UK number who lives in Latvia still gets texted in the UK.
        assert normalize_phone("+447700900123", "Latvia") == "+447700900123"


class TestCountryPrefixing:
    """A bare local number gets its country's dial code."""

    def test_local_number_gets_the_code(self):
        assert normalize_phone("20123456", "Latvia") == "+37120123456"

    def test_country_name_is_case_insensitive(self):
        assert normalize_phone("20123456", "  lAtViA ") == "+37120123456"

    def test_iso_code_works_too(self):
        assert normalize_phone("20123456", "LV") == "+37120123456"

    def test_trunk_zero_is_dropped(self):
        # 0 is a national prefix - it must not survive in front of the country code.
        assert normalize_phone("020123456", "Latvia") == "+37120123456"

    def test_a_different_country(self):
        assert normalize_phone("612345678", "Poland") == "+48612345678"


class TestRejected:
    """Bad input raises ValueError so the route can skip just that recipient."""

    @pytest.mark.parametrize("raw", [None, "", "   "])
    def test_missing_number(self, raw):
        with pytest.raises(ValueError, match="no phone number saved"):
            normalize_phone(raw, "Latvia")

    def test_unknown_country_without_a_prefix(self):
        with pytest.raises(ValueError, match="no dial code known"):
            normalize_phone("20123456", "Narnia")

    def test_letters_are_not_a_number(self):
        with pytest.raises(ValueError, match="not a usable phone number"):
            normalize_phone("call me", "Latvia")

    def test_too_short(self):
        with pytest.raises(ValueError, match="wrong number of digits"):
            normalize_phone("+3712", "Latvia")

    def test_too_long_for_e164(self):
        with pytest.raises(ValueError, match="wrong number of digits"):
            normalize_phone("+1234567890123456", "Latvia")


class TestDialCode:
    def test_known(self):
        assert dial_code("Latvia") == "371"

    @pytest.mark.parametrize("country", [None, "", "Narnia"])
    def test_unknown_is_none(self, country):
        assert dial_code(country) is None
