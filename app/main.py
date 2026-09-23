"""main.py - the FastAPI app: API routes plus the static frontend.

Routes stay thin. They validate input (Pydantic does that automatically),
call crud/auth, and return a schema. No SQL lives in this file.
"""
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

import auth
import crud
import notifications
from database import get_db
from models import User
from schema import (
    NotificationCreate,
    NotificationOut,
    RecipientCount,
    RecipientResult,
    Token,
    UserCreate,
    UserLogin,
    UserOut,
)

app = FastAPI(title="MNS - Medical Notification System")

# Only matters if you open the frontend from a *different* origin, e.g. VS Code
# Live Server on :5500. When FastAPI serves the frontend (the mount at the
# bottom of this file) everything is same-origin and CORS is not involved.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5500", "http://127.0.0.1:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------
# user system
# --------------------------------------------------------------------------

@app.post("/api/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(data: UserCreate, db: Session = Depends(get_db)):
    """Create an account. Returns the new user (never the password hash)."""
    if crud.get_user_by_email(db, data.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    return crud.create_user(db, data)


@app.post("/api/login", response_model=Token)
def login(data: UserLogin, db: Session = Depends(get_db)):
    """Exchange email + password for a JWT."""
    user = crud.get_user_by_email(db, data.email)

    # Deliberately the same error for "no such email" and "wrong password".
    # Different messages would let someone discover which emails are registered.
    if user is None or not auth.verify_password(data.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")

    return Token(access_token=auth.create_access_token(user.id))


@app.get("/api/me", response_model=UserOut)
def me(user: User = Depends(auth.get_current_user)):
    """The logged-in user's profile. Requires `Authorization: Bearer <token>`.

    Copy this Depends(...) line onto any future route that needs a login.
    """
    return user

# --------------------------------------------------------------------------
# notifications
#
# Both routes require a login. An unauthenticated send endpoint is an open
# SMS relay - anyone who finds the URL could run up the Twilio bill.
# --------------------------------------------------------------------------

@app.get("/api/notifications/recipients", response_model=RecipientCount)
def notification_recipients(
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """How many users can be texted, so the page can say so before sending."""
    return RecipientCount(recipients=crud.count_users_with_phone(db))


@app.post("/api/notifications/send", response_model=NotificationOut)
async def send_notification(
    data: NotificationCreate,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Text every user who gave a phone number at signup.

    The request carries only the message. Recipients come from the database,
    and each number is normalized using the country that user registered with.

    Numbers that cannot be normalized are skipped and reported by name - one
    unusable number must not cost everyone else their message.
    """
    recipients = crud.users_with_phone(db)
    if not recipients:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No user has a phone number saved",
        )

    # Normalize first, so we know who is actually sendable before we call out.
    results: list[RecipientResult] = []
    sendable: list[tuple[int, str]] = []

    for person in recipients:
        display_name = f"{person.name} {person.surname}"
        try:
            number = notifications.normalize_phone(person.phone, person.country)
        except ValueError as exc:
            results.append(RecipientResult(
                user_id=person.id, name=display_name, phone=person.phone,
                status="skipped", detail=str(exc),
            ))
            continue
        sendable.append((person.id, number))
        results.append(RecipientResult(
            user_id=person.id, name=display_name, phone=number, status="pending",
        ))

    outcomes = await notifications.send_batch([n for _, n in sendable], data.message)

    by_user = {user_id: outcome for (user_id, _), outcome in zip(sendable, outcomes)}
    for result in results:
        outcome = by_user.get(result.user_id)
        if outcome is not None:
            result.status = outcome["status"]
            result.detail = outcome["detail"]

    return NotificationOut(
        dry_run=not notifications.is_configured(),
        sent=sum(1 for r in results if r.status in ("sent", "dry_run")),
        skipped=sum(1 for r in results if r.status == "skipped"),
        failed=sum(1 for r in results if r.status == "failed"),
        results=results,
    )


# --------------------------------------------------------------------------
# static frontend
#
# Mounted LAST on purpose: the /api routes above are matched first, and
# anything left over is served as a file from app/static/.
# html=True means "/" serves index.html.
# --------------------------------------------------------------------------
app.mount(
    "/",
    StaticFiles(directory=Path(__file__).parent / "static", html=True),
    name="static",
)
