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
from database import get_db
from models import User
from schema import Token, UserCreate, UserLogin, UserOut

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
