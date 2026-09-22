"""database.py - engine, session factory, Base, and the get_db dependency."""
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Load .env from next to this file, so it works no matter which directory
# uvicorn was started from.
load_dotenv(Path(__file__).parent / ".env")

# URL.create escapes special characters in the password for you
# (an f-string breaks if the password contains @ : / etc.)
DATABASE_URL = URL.create(
    drivername="mysql+pymysql",
    username=os.getenv("DB_USER", "mns_user"),
    password=os.getenv("DB_PASSWORD", ""),
    host=os.getenv("DB_HOST", "127.0.0.1"),
    port=int(os.getenv("DB_PORT", "3306")),
    database=os.getenv("DB_NAME", "MNS"),  # case-sensitive on Linux!
    query={"charset": "utf8mb4"},
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,   # test connection before use (MySQL drops idle ones)
    pool_recycle=3600,    # replace connections older than 1 h
    echo=False,           # True = print every SQL statement (useful for learning)
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 style base (replaces declarative_base())."""
    pass


def get_db():
    """FastAPI dependency: one database session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
