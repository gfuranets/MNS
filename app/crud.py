"""crud.py - every database read/write lives here.

Routes in main.py stay thin: they validate input, call a function from this
file, and shape the response. No SQL in the route handlers.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import auth
from models import User
from schema import UserCreate


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def create_user(db: Session, data: UserCreate) -> User:
    """Hash the password and insert the row.

    The caller is responsible for checking the email is free first -
    see the signup route in main.py.
    """
    user = User(
        email=data.email,
        password_hash=auth.hash_password(data.password),
        name=data.name,
        surname=data.surname,
        birth_date=data.birth_date,
        address=data.address,
        city=data.city,
        country=data.country,
        phone=data.phone,
    )
    db.add(user)
    db.commit()
    db.refresh(user)  # reload so user.id and user.created_at are populated
    return user


# --------------------------------------------------------------------------
# notifications
#
# Phone numbers come from signup, so "who can be texted" is simply everyone
# who filled that optional field in. Both queries share the same filter.
# --------------------------------------------------------------------------

_HAS_PHONE = (User.phone.is_not(None), User.phone != "")


def users_with_phone(db: Session) -> list[User]:
    """Every user who can receive an SMS, oldest account first."""
    return list(db.scalars(select(User).where(*_HAS_PHONE).order_by(User.id)))


def count_users_with_phone(db: Session) -> int:
    """How many users have a phone number, without loading them all."""
    return db.scalar(select(func.count(User.id)).where(*_HAS_PHONE)) or 0
