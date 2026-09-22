"""models.py - SQLAlchemy tables. These mirror query.sql exactly."""
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # login credentials
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(60), nullable=False)

    # profile
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    surname: Mapped[str] = mapped_column(String(40), nullable=False)
    birth_date: Mapped[date] = mapped_column(Date, nullable=False)
    address: Mapped[str] = mapped_column(String(50), nullable=False)
    city: Mapped[str] = mapped_column(String(20), nullable=False)
    country: Mapped[str] = mapped_column(String(20), nullable=False)

    # for SMS notifications; optional at signup
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"
