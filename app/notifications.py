"""notifications.py - turning a stored phone number into an SMS.

Two separate jobs live here, in the same spirit as auth.py:

  1. Numbers  - normalize_phone() turns whatever a user typed at signup into
                E.164 (+37120123456), which is the only format Twilio accepts.
  2. Sending  - send_batch() / send_sms() talk to Twilio.

If the Twilio variables are missing from .env the module runs in DRY RUN:
it logs each message and reports "dry_run" instead of sending. That keeps the
whole feature demoable without credentials, and flips to real sending the
moment you fill them in - no code change.
"""
import logging
import os
import re
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

SID = os.getenv("TWILIO_SID")
TOKEN = os.getenv("TWILIO_TOKEN")
FROM = os.getenv("TWILIO_FROM")

TWILIO_URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"

log = logging.getLogger(__name__)


def is_configured() -> bool:
    """True when all three Twilio variables are present in .env."""
    return bool(SID and TOKEN and FROM)


# --------------------------------------------------------------------------
# numbers
#
# `country` on the users table is free text - signup.html has a plain input -
# so the lookup is forgiving: case and spacing are ignored, and the common
# ISO codes are accepted alongside the English name.
# --------------------------------------------------------------------------

DIAL_CODES = {
    "latvia": "371", "lv": "371", "lva": "371",
    "lithuania": "370", "lt": "370", "ltu": "370",
    "estonia": "372", "ee": "372", "est": "372",
    "poland": "48", "pl": "48", "pol": "48",
    "germany": "49", "de": "49", "deu": "49",
    "france": "33", "fr": "33", "fra": "33",
    "spain": "34", "es": "34", "esp": "34",
    "italy": "39", "it": "39", "ita": "39",
    "netherlands": "31", "nl": "31", "nld": "31",
    "belgium": "32", "be": "32", "bel": "32",
    "sweden": "46", "se": "46", "swe": "46",
    "norway": "47", "no": "47", "nor": "47",
    "denmark": "45", "dk": "45", "dnk": "45",
    "finland": "358", "fi": "358", "fin": "358",
    "ireland": "353", "ie": "353", "irl": "353",
    "portugal": "351", "pt": "351", "prt": "351",
    "austria": "43", "at": "43", "aut": "43",
    "switzerland": "41", "ch": "41", "che": "41",
    "czechia": "420", "czech republic": "420", "cz": "420", "cze": "420",
    "slovakia": "421", "sk": "421", "svk": "421",
    "hungary": "36", "hu": "36", "hun": "36",
    "romania": "40", "ro": "40", "rou": "40",
    "bulgaria": "359", "bg": "359", "bgr": "359",
    "greece": "30", "gr": "30", "grc": "30",
    "croatia": "385", "hr": "385", "hrv": "385",
    "slovenia": "386", "si": "386", "svn": "386",
    "ukraine": "380", "ua": "380", "ukr": "380",
    "united kingdom": "44", "uk": "44", "gb": "44", "gbr": "44",
    "great britain": "44", "england": "44",
    "united states": "1", "usa": "1", "us": "1", "united states of america": "1",
    "canada": "1", "ca": "1", "can": "1",
    "australia": "61", "au": "61", "aus": "61",
    "new zealand": "64", "nz": "64", "nzl": "64",
    "india": "91", "in": "91", "ind": "91",
    "japan": "81", "jp": "81", "jpn": "81",
    "brazil": "55", "br": "55", "bra": "55",
    "mexico": "52", "mx": "52", "mex": "52",
    "south africa": "27", "za": "27", "zaf": "27",
    "turkey": "90", "tr": "90", "tur": "90",
    "israel": "972", "il": "972", "isr": "972",
    "georgia": "995", "ge": "995", "geo": "995",
}

# Everything a person might type as a separator, plus the (0) some people put
# between a country code and the rest of the number.
_JUNK = re.compile(r"[\s\-().]|\(0\)")


def dial_code(country: str | None) -> str | None:
    """The international dialling prefix for a country name, or None."""
    if not country:
        return None
    return DIAL_CODES.get(country.strip().lower())


def normalize_phone(raw: str | None, country: str | None) -> str:
    """Turn a stored number into E.164, using `country` when it has no prefix.

    Raises ValueError with a human-readable reason when that is not possible -
    the caller reports it per-recipient rather than failing the whole send.
    """
    if not raw or not raw.strip():
        raise ValueError("no phone number saved")

    number = _JUNK.sub("", raw.strip())

    if number.startswith("00"):        # 0037120123456 - the old way of writing +
        number = "+" + number[2:]

    if number.startswith("+"):
        digits = number[1:]
    else:
        code = dial_code(country)
        if code is None:
            raise ValueError(f"no dial code known for country {country!r}")
        # A leading 0 is a national trunk prefix and is dropped when the
        # country code goes on the front: 020 123 456 -> +371 20 123 456.
        digits = code + number.lstrip("0")

    if not digits.isdigit():
        raise ValueError(f"{raw!r} is not a usable phone number")
    if not 8 <= len(digits) <= 15:      # E.164 allows at most 15 digits
        raise ValueError(f"{raw!r} has the wrong number of digits")

    return "+" + digits


# --------------------------------------------------------------------------
# sending
# --------------------------------------------------------------------------

async def _send_one(client: httpx.AsyncClient, to: str, body: str) -> dict:
    """One Twilio call. Never raises - failures come back as a result dict."""
    try:
        r = await client.post(
            TWILIO_URL.format(sid=SID),
            auth=(SID, TOKEN),
            data={"From": FROM, "To": to, "Body": body},
        )
        r.raise_for_status()
        return {"status": "sent", "detail": r.json().get("sid")}
    except httpx.HTTPStatusError as e:
        # Twilio puts a readable explanation in the body - surface that rather
        # than a bare "400 Bad Request".
        try:
            detail = e.response.json().get("message", e.response.text)
        except ValueError:
            detail = e.response.text
        return {"status": "failed", "detail": f"Twilio: {detail}"}
    except httpx.HTTPError as e:
        return {"status": "failed", "detail": f"Could not reach Twilio: {e}"}


async def send_batch(numbers: list[str], body: str) -> list[dict]:
    """Send one message to many numbers. Results line up with `numbers`.

    One failure does not stop the rest: every number gets its own result.
    """
    if not numbers:
        return []

    if not is_configured():
        for number in numbers:
            log.warning("DRY RUN - would SMS %s: %s", number, body)
        return [
            {"status": "dry_run", "detail": "Twilio is not configured in .env"}
            for _ in numbers
        ]

    async with httpx.AsyncClient(timeout=15.0) as client:
        return [await _send_one(client, number, body) for number in numbers]


async def send_sms(to: str, body: str) -> dict:
    """Send to a single number. Thin wrapper around send_batch()."""
    return (await send_batch([to], body))[0]
