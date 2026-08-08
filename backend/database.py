"""
F1RaceOps — database engine and session setup.

Single source of truth for how the app connects to Postgres. Reads
DATABASE_URL from .env (same variable Alembic's env.py uses), so there's
one connection string shared by migrations, ingestion, and the API.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Copy to .env at the repo root."
    )

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_session() -> Session:
    """Return a new SQLAlchemy session. Caller is responsible for closing it
    (or use it as a context manager: `with get_session() as session:`).
    Used by ingestion scripts, which manage their own session lifecycle."""
    return SessionLocal()


def get_db():
    """FastAPI dependency: yields a session and guarantees it's closed after
    the request, even if the endpoint raises. Use via `Depends(get_db)`."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()