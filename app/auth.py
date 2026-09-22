"""auth.py - password hashing, JWT creation, and the "who is logged in" dependency.

Two separate jobs live here:

  1. Passwords  - hash_password / verify_password (bcrypt). The plaintext
                  password is never stored anywhere.
  2. Tokens     - create_access_token / get_current_user (JWT). After login the
                  client holds a signed token and sends it on every request as
                  `Authorization: Bearer <token>`.
"""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from database import get_db
from models import User

load_dotenv(Path(__file__).parent / ".env")

JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

if not JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET is not set. Copy app/.env.example to app/.env and fill it in."
    )

# Tells FastAPI to look for `Authorization: Bearer <token>`, and puts an
# "Authorize" button in the /docs page.
bearer_scheme = HTTPBearer(auto_error=False)


# --------------------------------------------------------------------------
# passwords
# --------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    """bcrypt hash. Output is always 60 chars, which is why the column is VARCHAR(60)."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time comparison - never compare hashes with ==."""
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# --------------------------------------------------------------------------
# tokens
# --------------------------------------------------------------------------

def create_access_token(user_id: int) -> str:
    """Sign a token saying "this is user <id>", valid for JWT_EXPIRE_MINUTES."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),  # PyJWT requires `sub` to be a string
        "iat": now,
        "exp": now + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency. Add it to any route that requires a logged-in user:

        @app.get("/api/me")
        def me(user: User = Depends(auth.get_current_user)):
            ...

    Raises 401 if the token is missing, malformed, expired, or points at a
    user who no longer exists.
    """
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise unauthorized

    try:
        payload = jwt.decode(
            credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM]
        )
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise unauthorized

    user = db.get(User, user_id)
    if user is None:
        raise unauthorized

    return user
