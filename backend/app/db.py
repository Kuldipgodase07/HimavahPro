"""Database layer. SQLite for the prototype; any SQLAlchemy URL (PostgreSQL/PostGIS) in production."""
from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import DATABASE_URL

_kwargs: dict = {}
if DATABASE_URL.startswith("sqlite"):
    _kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, future=True, **_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

# Register live change synchronization to MongoDB Atlas
try:
    from .mongodb import register_sqlalchemy_mongo_hooks
    register_sqlalchemy_mongo_hooks(SessionLocal)
except Exception:
    pass


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    """Naive UTC timestamps are stored throughout the prototype."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso(dt: datetime | None) -> str | None:
    return None if dt is None else dt.replace(microsecond=0).isoformat() + "Z"


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
