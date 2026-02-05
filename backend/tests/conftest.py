"""
Pytest Configuration Fixtures

Sets up test environment with isolated in-memory database.
"""
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models.base import Base

# Set test environment variables BEFORE importing app modules
# This ensures the config module can load successfully
os.environ.setdefault("GEMINI_API_KEY", "test_gemini_key_for_testing")
os.environ.setdefault("MOONSHOT_API_KEY", "test_moonshot_key_for_testing")
os.environ.setdefault("ZHIPU_API_KEY", "test_zhipu_key_for_testing")
os.environ.setdefault("HF_TOKEN", "test_hf_token_for_testing")


@pytest.fixture(scope="function")
def test_engine():
    """
    Create an isolated in-memory SQLite engine for testing.

    Each test function gets a fresh database.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def test_session(test_engine):
    """
    Create a database session for testing.

    All tables are created before the test and dropped after.
    """
    # Create all tables
    Base.metadata.create_all(test_engine)

    # Create session factory
    SessionFactory = sessionmaker(bind=test_engine)

    # Create session
    session = SessionFactory()
    yield session

    # Cleanup
    session.close()
    Base.metadata.drop_all(test_engine)


@pytest.fixture(scope="session")
def test_api_keys():
    """
    Provide test API keys for tests that need them.
    Returns a dictionary with all required keys.
    """
    return {
        "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY", "test_gemini_key"),
        "MOONSHOT_API_KEY": os.environ.get("MOONSHOT_API_KEY", "test_moonshot_key"),
        "ZHIPU_API_KEY": os.environ.get("ZHIPU_API_KEY", "test_zhipu_key"),
        "HF_TOKEN": os.environ.get("HF_TOKEN", "test_hf_token"),
    }
