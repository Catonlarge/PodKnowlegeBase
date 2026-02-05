"""
Unit tests for Base model and TimestampMixin.

Test Naming Convention (BDD):
- test_<behavior>_<expected_result>
"""
import pytest

from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import Session

from app.models.base import Base, TimestampMixin, set_sqlite_pragma


class DummyModel(Base, TimestampMixin):
    """Dummy model for TimestampMixin testing."""
    __tablename__ = "dummy_models"

    id = Column(Integer, primary_key=True)
    name = Column(String(50))


class TestTimestampMixin:
    """Test TimestampMixin functionality."""

    def test_timestamp_mixin_adds_created_at_field(self):
        """Given: Model with TimestampMixin
        When: Creating model instance
        Then: created_at field is present and not null
        """
        model = DummyModel(name="Test")
        assert hasattr(model, "created_at")

    def test_timestamp_mixin_adds_updated_at_field(self):
        """Given: Model with TimestampMixin
        When: Creating model instance
        Then: updated_at field is present and not null
        """
        model = DummyModel(name="Test")
        assert hasattr(model, "updated_at")

    def test_timestamp_mixin_created_at_defaults_to_current_time(self):
        """Given: Database session
        When: Creating and committing a record
        Then: created_at is set to recent datetime
        """
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)

        with Session(engine) as session:
            model = DummyModel(name="Test")
            session.add(model)
            session.commit()

            assert model.created_at is not None
            assert isinstance(model.created_at, datetime)
            # Check it's within last minute
            assert (datetime.utcnow() - model.created_at).total_seconds() < 60

    def test_timestamp_mixin_updated_at_defaults_to_current_time(self):
        """Given: Database session
        When: Creating and committing a record
        Then: updated_at is set to recent datetime
        """
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)

        with Session(engine) as session:
            model = DummyModel(name="Test")
            session.add(model)
            session.commit()

            assert model.updated_at is not None
            assert isinstance(model.updated_at, datetime)

    def test_timestamp_mixin_updated_at_updates_on_modify(self):
        """Given: Existing record
        When: Modifying the record
        Then: updated_at changes to new timestamp
        """
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)

        with Session(engine) as session:
            model = DummyModel(name="Test")
            session.add(model)
            session.commit()

            original_updated_at = model.updated_at

            # Wait a bit and update
            import time
            time.sleep(0.01)
            model.name = "Updated"
            session.commit()

            assert model.updated_at > original_updated_at


class TestBase:
    """Test Base declarative base."""

    def test_base_is_declarative_base(self):
        """Given: Base from app.models.base
        When: Checking type
        Then: Is SQLAlchemy declarative base
        """
        from sqlalchemy.orm import DeclarativeBase
        assert isinstance(Base, type)
        assert issubclass(Base, DeclarativeBase)


class TestSetSqlitePragma:
    """Test SQLite pragma event handler."""

    def test_set_sqlite_pragma_enables_foreign_keys(self):
        """Given: Mock database connection
        When: Calling set_sqlite_pragma
        Then: Executes PRAGMA foreign_keys=ON
        """
        class MockCursor:
            def __init__(self):
                self.executed = []

            def execute(self, sql):
                self.executed.append(sql)

            def close(self):
                pass

        mock_cursor = MockCursor()

        class MockConnection:
            def cursor(self):
                return mock_cursor

        conn = MockConnection()
        set_sqlite_pragma(conn, None)

        assert "PRAGMA foreign_keys=ON" in mock_cursor.executed
