"""mailer.py - reminder emails through Gmail.

Same shape as notifications.py (SMS): one send function that never raises
and returns {"status", "detail"}, and a DRY RUN when .env has no Gmail
credentials - the message is logged instead of sent.

Gmail setup: turn on 2-Step Verification for the account, create an App
Password at https://myaccount.google.com/apppasswords and put both in .env:

  GMAIL_USER=yourapp@gmail.com
  GMAIL_APP_PASSWORD=abcd efgh ijkl mnop

Gmail allows roughly 500 messages a day from a normal account - plenty for
a demo. For real traffic swap _send() for a transactional provider.
"""
import asyncio
import logging
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

USER = os.getenv("GMAIL_USER", "").strip()
# Google shows the app password in groups of four; the spaces are not part of it.
PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "")
SENDER_NAME = os.getenv("GMAIL_SENDER_NAME", "MNS reminders")

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465   # implicit TLS

log = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(USER and PASSWORD)


def _send(to: str, subject: str, body: str) -> None:
    """Blocking SMTP call - run it in a thread."""
    msg = EmailMessage()
    msg["From"] = f"{SENDER_NAME} <{USER}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
        smtp.login(USER, PASSWORD)
        smtp.send_message(msg)


async def send_email(to: str | None, subject: str, body: str) -> dict:
    """Send one email. Never raises - failures come back as a result dict."""
    if not to:
        return {"status": "skipped", "detail": "no email address"}
    if not is_configured():
        log.warning("DRY RUN - would email %s: %s", to, subject)
        return {"status": "dry_run", "detail": "Gmail is not configured in .env"}
    try:
        await asyncio.to_thread(_send, to, subject, body)
        return {"status": "sent", "detail": None}
    except smtplib.SMTPAuthenticationError:
        return {"status": "failed", "detail": "Gmail rejected the login - check GMAIL_APP_PASSWORD"}
    except (smtplib.SMTPException, OSError) as e:
        return {"status": "failed", "detail": f"Gmail: {e}"}
