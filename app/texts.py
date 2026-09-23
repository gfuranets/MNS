"""texts.py - the words the server sends: reminder pop-ups, SMS, prep alerts.

The app UI translates itself (static/i18n.js). These are the only texts
generated on the server, because they leave it as SMS or get stored in the
inbox - so they are written in the user's language at send time.

Latvian numbers change the noun's case depending on the preposition:
  pēc / pirms + 1  -> genitive singular  (pēc 1 dienas)
  par         + 1  -> accusative singular (par 1 dienu)
  any + 2, 5, 12.. -> dative plural       (pēc 12 dienām, par 3 mēnešiem)
Numbers ending in 1 (but not 11) take the singular: 21 dienas, 11 dienām.
"""
from datetime import datetime

_EN_UNITS = {"day": "day", "week": "week", "month": "month", "year": "year"}
_LV_UNITS = {
    #        genitive sg, accusative sg, dative pl
    "day":   ("dienas", "dienu", "dienām"),
    "week":  ("nedēļas", "nedēļu", "nedēļām"),
    "month": ("mēneša", "mēnesi", "mēnešiem"),
    "year":  ("gada", "gadu", "gadiem"),
}


def _amount(days: int) -> tuple[int, str]:
    """12 days / 3 weeks / 4 months / 2 years - whichever reads naturally."""
    days = abs(days)
    if days < 14:
        return days, "day"
    if days < 60:
        return days // 7, "week"
    if days < 730:
        return days // 30, "month"
    return days // 365, "year"


def span(days: int, language: str = "en", case: str = "gen") -> str:
    """A length of time for use after a preposition.

    case (Latvian only): "gen" after pēc/pirms, "acc" after par.
    """
    n, unit = _amount(days)
    if language == "lv":
        genitive, accusative, dative_pl = _LV_UNITS[unit]
        singular = n % 10 == 1 and n % 100 != 11
        return f"{n} {(genitive if case == 'gen' else accusative) if singular else dative_pl}"
    return f"{n} {_EN_UNITS[unit]}{'' if n == 1 else 's'}"


def status_line(item, language: str = "en") -> str:
    """Short status, e.g. for an SMS list: "overdue by 3 months"."""
    lv = language == "lv"
    if item.kind == "guideline" and item.last_done is None:
        return "nav ieraksta" if lv else "no record yet"
    if item.days < 0:
        return f"nokavēts par {span(item.days, language, 'acc')}" if lv \
            else f"overdue by {span(item.days)}"
    if item.days == 0:
        return "šodien" if lv else "due today"
    return f"pēc {span(item.days, language)}" if lv else f"due in {span(item.days)}"


def push_text(item, language: str = "en") -> str:
    """The pop-up / inbox text for one due item."""
    name, lv = item.name, language == "lv"

    if item.kind == "guideline" and item.last_done is None:
        return (f"{name}: vēl nav ieraksta. Piesakieties vai ierakstiet, ja tas jau ir izdarīts."
                if lv else f"No record of your {name.lower()} yet. Book it, or log it if you've had one.")
    if item.days < 0:
        if item.kind == "task":
            return (f"{name}: termiņš bija pirms {span(item.days, language)}. "
                    "Atzīmējiet, vai tas ir paveikts vai nokavēts."
                    if lv else f"{name} was due {span(item.days)} ago. Mark it done or missed.")
        return (f"{name}: nokavēts par {span(item.days, language, 'acc')}. "
                "Piesakieties vai atzīmējiet kā paveiktu, ja jau bijāt."
                if lv else f"{name} is overdue by {span(item.days)}. Book it, or mark it done if you already went.")
    if item.days == 0:
        return f"{name}: termiņš ir šodien." if lv else f"{name} is due today."
    return (f"{name}: termiņš pēc {span(item.days, language)}."
            if lv else f"{name} is due in {span(item.days)}.")


def sms_text(first_name: str, items: list, language: str = "en") -> str:
    """One text for the whole batch - five separate SMS would be spam."""
    lines = "; ".join(f"{i.name} ({status_line(i, language)})" for i in items)
    if language == "lv":
        return f"Sveiki, {first_name}! Veselības atgādinājums: {lines}. Atveriet lietotni, lai atzīmētu paveikto."
    return f"Hi {first_name}, health reminder: {lines}. Open the app to mark them done."


def prep_text(procedure: str, appointment_at: datetime, step: str, language: str = "en") -> str:
    """A procedure-preparation reminder: what to do now, for which appointment."""
    if language == "lv":
        return f"{procedure}, {appointment_at:%d.%m.} plkst. {appointment_at:%H:%M}: {step}"
    return f"{procedure}, {appointment_at:%d %b} at {appointment_at:%H:%M}: {step}"
