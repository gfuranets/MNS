"""schema.py - Pydantic models: the shape of data going in and out of the API.

Keep these separate from models.py. models.py describes the database;
schema.py describes the JSON contract. UserOut has no password_hash field,
so a hash can never leak out through a response even by accident.
"""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    """Body of POST /api/signup."""
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)  # bcrypt caps at 72 bytes
    name: str = Field(min_length=1, max_length=40)
    surname: str = Field(min_length=1, max_length=40)
    birth_date: date
    address: str = Field(min_length=1, max_length=50)
    city: str = Field(min_length=1, max_length=20)
    country: str = Field(min_length=1, max_length=20)
    phone: str | None = Field(default=None, max_length=20)


class UserLogin(BaseModel):
    """Body of POST /api/login."""
    email: EmailStr
    password: str


class UserOut(BaseModel):
    """What the API returns about a user. Deliberately has no password field."""
    model_config = ConfigDict(from_attributes=True)  # lets us build it from a User row

    id: int
    email: EmailStr
    name: str
    surname: str
    birth_date: date
    address: str
    city: str
    country: str
    phone: str | None
    created_at: datetime


class Token(BaseModel):
    """What POST /api/login returns."""
    access_token: str
    token_type: str = "bearer"


class AddBloodResults(BaseModel):
    """Placeholder - the blood sample feature is the next slice."""
    pass
