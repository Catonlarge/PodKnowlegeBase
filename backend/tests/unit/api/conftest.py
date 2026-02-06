"""
API Tests Fixtures

Shared fixtures for API unit tests.
"""
from typing import AsyncGenerator, Generator

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_session
from app.models import Episode, AudioSegment, TranscriptCue, Chapter, Translation
from app.enums.workflow_status import WorkflowStatus
from tests.conftest import test_session


# ==================== Test Client Override ====================


def override_get_session():
    """Override database session for testing"""
    return test_session


@pytest.fixture(autouse=True)
def override_database_dependency():
    """Automatically override database dependency for all tests"""
    app.dependency_overrides[get_session] = override_get_session
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client(override_database_dependency) -> Generator[TestClient, None, None]:
    """
    FastAPI test client with database override.

    Usage:
        def test_create_episode(client):
            response = client.post("/api/v1/episodes", json={"url": "https://youtube.com/watch?v=test"})
            assert response.status_code == 200
    """
    with TestClient(app) as test_client:
        yield test_client


# ==================== Test Data Fixtures ====================


@pytest.fixture
def sample_episode(test_session) -> Episode:
    """Create a sample Episode for testing"""
    episode = Episode(
        title="Test Episode",
        file_hash="test_hash_123",
        source_url="https://youtube.com/watch?v=test123",
        duration=300.0,
        workflow_status=WorkflowStatus.READY_FOR_REVIEW.value,
    )
    test_session.add(episode)
    test_session.commit()
    test_session.refresh(episode)
    return episode


@pytest.fixture
def sample_episode_with_content(sample_episode: Episode, test_session) -> Episode:
    """Create a sample Episode with segments, cues, and chapters"""
    # Create AudioSegment
    segment = AudioSegment(
        episode_id=sample_episode.id,
        segment_index=0,
        segment_id="seg_001",
        start_time=0.0,
        end_time=180.0,
        status="completed",
    )
    test_session.add(segment)
    test_session.flush()

    # Create TranscriptCues
    for i in range(3):
        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=float(i * 10),
            end_time=float((i + 1) * 10),
            speaker="Speaker A",
            text=f"Sample text {i}",
            chapter_id=None,
        )
        test_session.add(cue)

    # Create Chapter
    chapter = Chapter(
        episode_id=sample_episode.id,
        chapter_index=0,
        title="Test Chapter",
        summary="Test chapter summary",
        start_time=0.0,
        end_time=30.0,
        status="completed",
    )
    test_session.add(chapter)
    test_session.flush()

    # Link cues to chapter
    for cue in segment.transcript_cues:
        cue.chapter_id = chapter.id

    test_session.commit()
    test_session.refresh(sample_episode)
    return sample_episode


@pytest.fixture
def sample_translation(sample_episode_with_content: Episode, test_session) -> Translation:
    """Create a sample Translation for testing"""
    cue = sample_episode_with_content.transcript_cues[0]
    translation = Translation(
        cue_id=cue.id,
        language_code="zh",
        translation="示例翻译",
        original_translation="示例翻译",
        translation_status="completed",
    )
    test_session.add(translation)
    test_session.commit()
    test_session.refresh(translation)
    return translation


# ==================== Request Data Fixtures ====================


@pytest.fixture
def episode_create_request() -> dict:
    """Sample episode create request"""
    return {
        "url": "https://youtube.com/watch?v=test123",
        "title": "Test Episode Title"
    }


@pytest.fixture
def episode_update_request() -> dict:
    """Sample episode update request"""
    return {
        "title": "Updated Title",
        "ai_summary": "Updated summary"
    }


@pytest.fixture
def translation_update_request() -> dict:
    """Sample translation update request"""
    return {
        "translation": "修正后的翻译"
    }
