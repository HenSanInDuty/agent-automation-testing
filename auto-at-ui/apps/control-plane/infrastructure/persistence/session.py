"""Session construction and transaction boundaries for application use cases."""

from collections.abc import Callable, Generator
from contextlib import contextmanager

from config import Settings
from sqlalchemy import Engine
from sqlalchemy import create_engine as create_sqlalchemy_engine
from sqlalchemy.orm import Session, sessionmaker


def sqlalchemy_database_url(database_url: str) -> str:
    """Use psycopg 3 for PostgreSQL while preserving test/other SQLAlchemy URLs."""
    return database_url.replace("postgresql://", "postgresql+psycopg://", 1)


def create_engine(settings: Settings) -> Engine:
    return create_sqlalchemy_engine(
        sqlalchemy_database_url(settings.database_url), pool_pre_ping=True
    )


def create_session_factory(settings: Settings) -> sessionmaker[Session]:
    return sessionmaker(bind=create_engine(settings), expire_on_commit=False)


@contextmanager
def transactional_session(
    factory: Callable[[], Session],
) -> Generator[Session, None, None]:
    """Commit all related writes together, or rollback them all on failure."""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
