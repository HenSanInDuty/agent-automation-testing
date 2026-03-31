from collections.abc import Generator

from app.config import settings
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# ── Engine ────────────────────────────────────────────────────────────────────

engine = create_engine(
    settings.DATABASE_URL,
    # SQLite-specific: allow the same connection to be used across threads
    connect_args={"check_same_thread": False},
    # Echo SQL in development for easier debugging
    echo=settings.is_development,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    """
    Apply recommended SQLite pragmas on every new connection:
    - WAL mode    → better concurrent read/write performance
    - foreign_keys → enforce FK constraints (SQLite disables them by default)
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# ── Session factory ───────────────────────────────────────────────────────────

SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # keep attributes accessible after commit
)


# ── Declarative base ──────────────────────────────────────────────────────────


class Base(DeclarativeBase):
    """All ORM models inherit from this class."""

    pass


# ── Helpers ───────────────────────────────────────────────────────────────────


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a DB session and ensures it is closed
    even if an exception occurs.

    Usage:
        @router.get("/items")
        def list_items(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables() -> None:
    """Create all tables that are registered on Base.metadata."""
    # Import models here so they are registered before create_all is called
    from app.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def drop_tables() -> None:
    """Drop all tables — use only in tests / dev environments."""
    from app.db import models  # noqa: F401

    Base.metadata.drop_all(bind=engine)


def check_connection() -> bool:
    """Quick health-check: return True if the DB is reachable."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
