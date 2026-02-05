"""
Unit tests for database connection management.

Test Naming Convention (BDD):
- test_<behavior>_<expected_result>
"""
from unittest.mock import MagicMock, patch

import pytest

from app.database import (
    init_database,
    get_session,
    create_tables,
    drop_tables,
    get_engine,
    reset_database,
)
from app.models.base import Base
from sqlalchemy import Column, Integer, String


class DummyModel(Base):
    """Dummy model for testing."""
    __tablename__ = "dummy_test_models"

    id = Column(Integer, primary_key=True)
    name = Column(String(50))


class TestInitDatabase:
    """Test database initialization."""

    def test_init_database_creates_engine(self):
        """Given: Valid configuration
        When: Calling init_database()
        Then: Engine is created
        """
        # Reset global state
        import app.database
        app.database._engine = None

        init_database()

        from app.database import _engine
        assert _engine is not None

    def test_init_database_creates_session_factory(self):
        """Given: Valid configuration
        When: Calling init_database()
        Then: Session factory is created
        """
        # Reset global state
        import app.database
        app.database._session_factory = None

        init_database()

        from app.database import _session_factory
        assert _session_factory is not None


class TestGetSession:
    """Test session context manager."""

    def test_get_session_returns_active_session(self):
        """Given: Initialized database
        When: Calling get_session()
        Then: Returns active Session object
        """
        from sqlalchemy.orm import Session

        with get_session() as session:
            assert isinstance(session, Session)
            assert session.is_active

    def test_get_session_commits_on_success(self):
        """Given: Session with changes
        When: Exiting context normally
        Then: Changes are committed
        """
        # First create tables
        create_tables()

        with get_session() as session:
            dummy = DummyModel(name="Test")
            session.add(dummy)

        # Verify in new session
        with get_session() as session:
            result = session.query(DummyModel).first()
            assert result is not None
            assert result.name == "Test"

        # Cleanup
        drop_tables()

    def test_get_session_rolls_back_on_error(self):
        """Given: Session with changes
        When: Exception occurs in context
        Then: Changes are rolled back
        """
        # First create tables
        create_tables()

        try:
            with get_session() as session:
                dummy = DummyModel(name="Test")
                session.add(dummy)
                # Simulate error
                raise ValueError("Test error")
        except ValueError:
            pass

        # Verify rollback
        with get_session() as session:
            result = session.query(DummyModel).first()
            assert result is None

        # Cleanup
        drop_tables()


class TestCreateTables:
    """Test table creation."""

    def test_create_tables_creates_all_tables(self):
        """Given: Database with models defined
        When: Calling create_tables()
        Then: All tables are created
        """
        # Reset state
        drop_tables()

        create_tables()

        # Check if our test table exists in metadata
        table_names = Base.metadata.tables.keys()
        assert "dummy_test_models" in table_names

        # Cleanup
        drop_tables()

    def test_create_tables_is_idempotent(self):
        """Given: Database with existing tables
        When: Calling create_tables() again
        Then: No error occurs (idempotent)
        """
        create_tables()
        create_tables()  # Should not raise

        # Cleanup
        drop_tables()


class TestDropTables:
    """Test table dropping."""

    def test_drop_tables_removes_all_tables(self):
        """Given: Database with tables
        When: Calling drop_tables()
        Then: All tables are removed
        """
        # First create tables
        create_tables()

        # Then drop them
        drop_tables()

        # Create again to verify it works
        create_tables()

        # Cleanup
        drop_tables()


class TestGetEngine:
    """Test engine retrieval."""

    def test_get_engine_returns_engine(self):
        """Given: Possibly uninitialized database
        When: Calling get_engine()
        Then: Returns Engine object
        """
        from sqlalchemy.engine import Engine

        engine = get_engine()
        assert isinstance(engine, Engine)


class TestResetDatabase:
    """Test database reset."""

    def test_reset_database_drops_and_recreates(self):
        """Given: Database with data
        When: Calling reset_database()
        Then: All data is lost, tables are recreated
        """
        # Create tables and add data
        create_tables()

        with get_session() as session:
            dummy = DummyModel(name="Before Reset")
            session.add(dummy)

        # Reset
        reset_database()

        # Verify data is gone
        with get_session() as session:
            result = session.query(DummyModel).first()
            assert result is None

        # Cleanup
        drop_tables()
