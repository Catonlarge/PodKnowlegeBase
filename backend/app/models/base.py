"""
SQLAlchemy Base Model and Mixins

This module defines the declarative base and common mixins for all models.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, declarative_mixin


class Base(DeclarativeBase):
    """Custom declarative base for all models."""
    pass


@declarative_mixin
class TimestampMixin:
    """
    Mixin that adds timestamp fields to a model.

    Attributes:
        created_at: DateTime when the record was created
        updated_at: DateTime when the record was last updated
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        doc="Timestamp when the record was created"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
        doc="Timestamp when the record was last updated"
    )


# Enable foreign key constraints for SQLite
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """
    Enable foreign key constraints for SQLite.

    SQLite has foreign keys disabled by default. This event listener
    enables them when the database connection is established.
    """
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
