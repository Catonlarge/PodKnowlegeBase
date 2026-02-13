"""
Database Connection Management

This module provides database connection and session management for the application.
It uses SQLAlchemy 2.0+ with async support and context managers for safe resource handling.
"""
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import BASE_DIR, DATABASE_PATH, DATABASE_ECHO
from app.models.base import Base


# SQLite busy timeout (ms). Default 5s is too short when Obsidian/other tools hold the DB.
SQLITE_BUSY_TIMEOUT_MS = 30000


def _set_sqlite_pragma(dbapi_conn, connection_record):
    """Enable WAL mode and busy_timeout for SQLite (reduces 'database is locked' errors)."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
    cursor.close()


# Global variables for engine and session factory
_engine: Optional[object] = None
_session_factory: Optional[sessionmaker] = None


def init_database() -> None:
    """
    Initialize the database connection.

    Creates the database engine and session factory.
    The database file is created automatically if it doesn't exist.
    """
    global _engine, _session_factory

    # Ensure the database directory exists
    db_path = Path(DATABASE_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Create SQLite database URL
    database_url = f"sqlite:///{DATABASE_PATH}"

    # Create engine with echo option for debugging
    _engine = create_engine(
        database_url,
        echo=DATABASE_ECHO,
        connect_args={
            "check_same_thread": False,
            "timeout": SQLITE_BUSY_TIMEOUT_MS / 1000,
        },
    )
    event.listen(_engine, "connect", _set_sqlite_pragma)

    # Create session factory
    _session_factory = sessionmaker(
        bind=_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Get a database session (context manager).

    Automatically handles session lifecycle:
    - Opens session on entry
    - Commits on success, rolls back on error
    - Closes session on exit

    Yields:
        Session: SQLAlchemy session object

    Example:
        with get_session() as session:
            episode = session.query(Episode).first()
            episode.title = "New Title"
            session.commit()
    """
    if _session_factory is None:
        init_database()

    session = _session_factory()
    try:
        yield session
        # Only commit if no exception occurred and session is active
        if session.is_active:
            session.commit()
    except Exception:
        # Rollback on error
        session.rollback()
        raise
    finally:
        # Always close the session
        session.close()


def create_tables() -> None:
    """
    Create all database tables.

    This function creates all tables defined in the models.
    It uses `create_all()` which is idempotent - existing tables
    are not modified.

    Note:
        This does not handle schema migrations. For production,
        consider using Alembic for migration management.
    """
    if _engine is None:
        init_database()

    Base.metadata.create_all(_engine)


def drop_tables() -> None:
    """
    Drop all database tables.

    Warning:
        This will delete all data! Use only for testing or
        complete database resets.
    """
    if _engine is None:
        init_database()

    Base.metadata.drop_all(_engine)


def get_engine() -> object:
    """
    Get the database engine.

    Returns:
        Engine: SQLAlchemy engine instance

    Raises:
        RuntimeError: If database has not been initialized
    """
    if _engine is None:
        init_database()
    return _engine


def reset_database() -> None:
    """
    Reset the database by dropping and recreating all tables.

    Warning:
        This will delete all data! Use only for testing.
    """
    drop_tables()
    create_tables()
