"""crud.py - every database read/write lives here.

Routes in main.py stay thin: they validate input, call a function from this
file, and shape the response. No SQL in the route handlers.
"""
from sqlalchemy import select
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
