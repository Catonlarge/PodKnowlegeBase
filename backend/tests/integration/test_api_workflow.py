"""
API Workflow Integration Tests

Tests end-to-end API workflows across all modules.
Tests Episode CRUD, Transcripts, Translations, Chapters, Marketing, and Publications.
"""
import hashlib
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_session
from app.models import (
    Base, Episode, AudioSegment, TranscriptCue, Translation,
    Chapter, MarketingPost, PublicationRecord
)
from app.enums.workflow_status import WorkflowStatus
from app.enums.translation_status import TranslationStatus
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def calculate_url_hash(url: str) -> str:
    """Calculate URL hash matching API implementation."""
    return hashlib.md5(url.encode()).hexdigest()


# =============================================================================
# Test Database Setup for API Tests
# =============================================================================

@pytest.fixture(scope="function")
def api_test_engine():
    """
    Create isolated in-memory SQLite database for API integration tests.

    Uses shared cache mode to allow multiple connections to the same
    in-memory database (needed for FastAPI TestClient).
    """
    engine = create_engine(
        "sqlite:///file:memorydb?mode=memory&cache=shared",
        connect_args={"check_same_thread": False},
    )
    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def api_test_session(api_test_engine):
    """Create database session for API integration tests."""
    Base.metadata.create_all(api_test_engine)

    # Use same options as production database
    SessionFactory = sessionmaker(
        bind=api_test_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    session = SessionFactory()

    yield session

    session.close()
    Base.metadata.drop_all(api_test_engine)


@pytest.fixture(scope="function")
def api_client(api_test_session):
    """Create FastAPI test client with database override."""
    def override_get_session():
        yield api_test_session

    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


# =============================================================================
# Helper Fixtures
# =============================================================================

@pytest.fixture(scope="function")
def full_episode_with_content(api_test_session):
    """
    Create complete Episode data for API testing.
    Includes Episode, AudioSegment, TranscriptCues, Translations, and Chapters.
    """
    # Create Episode
    episode = Episode(
        title="API Integration Test Episode",
        file_hash="api_integration_hash_123",
        duration=300.0,
        source_url="https://youtube.com/watch?v=api_test_123",
        ai_summary="This is an API integration test episode.",
        workflow_status=WorkflowStatus.TRANSLATED.value
    )
    api_test_session.add(episode)
    api_test_session.flush()

    # Create AudioSegment
    segment = AudioSegment(
        episode_id=episode.id,
        segment_index=0,
        segment_id="segment_api_001",
        start_time=0.0,
        end_time=300.0,
        status="completed"
    )
    api_test_session.add(segment)
    api_test_session.flush()

    # Create Chapters
    chapters = []
    for i in range(2):
        chapter = Chapter(
            episode_id=episode.id,
            chapter_index=i,
            title=f"Chapter {i + 1}",
            summary=f"Summary for chapter {i + 1}",
            start_time=i * 150.0,
            end_time=(i + 1) * 150.0,
            status="completed"
        )
        chapters.append(chapter)
        api_test_session.add(chapter)
    api_test_session.flush()

    # Create TranscriptCues with chapter associations
    cues = []
    for i in range(6):
        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=i * 50.0,
            end_time=(i + 1) * 50.0,
            speaker="SPEAKER_00" if i % 2 == 0 else "SPEAKER_01",
            text=f"This is test sentence {i} for API integration testing."
        )
        chapter_index = 0 if i < 3 else 1
        cue.chapter_id = chapters[chapter_index].id
        cues.append(cue)
        api_test_session.add(cue)
    api_test_session.flush()

    # Create Translations
    for cue in cues:
        translation = Translation(
            cue_id=cue.id,
            language_code="zh",
            translation=f"这是测试句子 {cue.id}。",
            original_translation=f"这是测试句子 {cue.id}。",
            is_edited=False,
            translation_status=TranslationStatus.COMPLETED.value
        )
        api_test_session.add(translation)
    api_test_session.flush()

    return episode


# =============================================================================
# Episode API Workflow Tests
# =============================================================================

class TestEpisodeAPIWorkflow:
    """Episode API end-to-end workflow tests."""

    def test_create_episode_duplicate_returns_existing(self, api_client, api_test_session):
        """
        Behavior: Creating episode with duplicate URL returns existing episode

        Given:
            - An existing episode in database
        When:
            - POST /api/v1/episodes with same URL
        Then:
            - Returns existing episode (201 with existing data)
            - Does not create duplicate
        """
        # Arrange - Create existing episode with correct hash
        test_url = "https://youtube.com/watch?v=duplicate_test"
        url_hash = calculate_url_hash(test_url)

        existing = Episode(
            title="Existing Episode",
            file_hash=url_hash,
            source_url=test_url,
            duration=100.0,
            workflow_status=WorkflowStatus.READY_FOR_REVIEW.value
        )
        api_test_session.add(existing)
        api_test_session.commit()

        # Verify episode was created
        queried = api_test_session.query(Episode).filter(Episode.file_hash == url_hash).first()
        assert queried is not None, f"Episode not found in database after commit"

        # Act - Create duplicate
        response = api_client.post(
            "/api/v1/episodes",
            json={"url": test_url}
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == existing.id
        assert data["title"] == "Existing Episode"

        # Verify no duplicate created
        count = api_test_session.query(Episode).filter(
            Episode.file_hash == url_hash
        ).count()
        assert count == 1

    def test_create_list_get_update_delete_workflow(self, api_client):
        """
        Behavior: Full Episode CRUD workflow

        Given:
            - Empty database
        When:
            1. Create new episode
            2. List episodes
            3. Get episode details
            4. Update episode
            5. Delete episode
        Then:
            - All operations succeed
        """
        # Act 1: Create episode
        create_response = api_client.post(
            "/api/v1/episodes",
            json={
                "url": "https://youtube.com/watch?v=crud_test_123",
                "title": "CRUD Test Episode"
            }
        )
        assert create_response.status_code == 201
        episode_id = create_response.json()["id"]

        # Act 2: List episodes
        list_response = api_client.get("/api/v1/episodes")
        assert list_response.status_code == 200
        list_data = list_response.json()
        assert list_data["total"] == 1
        assert len(list_data["items"]) == 1

        # Act 3: Get episode details
        get_response = api_client.get(f"/api/v1/episodes/{episode_id}")
        assert get_response.status_code == 200
        detail_data = get_response.json()
        assert detail_data["id"] == episode_id
        assert detail_data["title"] == "CRUD Test Episode"

        # Act 4: Update episode
        update_response = api_client.patch(
            f"/api/v1/episodes/{episode_id}",
            json={"title": "Updated CRUD Test Episode"}
        )
        assert update_response.status_code == 200
        update_data = update_response.json()
        assert update_data["title"] == "Updated CRUD Test Episode"

        # Act 5: Delete episode
        delete_response = api_client.delete(f"/api/v1/episodes/{episode_id}")
        assert delete_response.status_code == 200

        # Verify deleted
        get_deleted = api_client.get(f"/api/v1/episodes/{episode_id}")
        assert get_deleted.status_code == 404

    def test_list_episodes_with_filters(self, api_client, api_test_session):
        """
        Behavior: List episodes with status and pagination filters

        Given:
            - Multiple episodes with different statuses
        When:
            - GET /api/v1/episodes with status filter and pagination
        Then:
            - Returns filtered and paginated results
        """
        # Arrange - Create episodes
        statuses = [
            WorkflowStatus.READY_FOR_REVIEW.value,
            WorkflowStatus.PUBLISHED.value,
            WorkflowStatus.READY_FOR_REVIEW.value,
        ]
        for i, status in enumerate(statuses):
            episode = Episode(
                title=f"Episode {i}",
                file_hash=f"filter_hash_{i}",
                source_url=f"https://youtube.com/watch?v=filter_{i}",
                duration=100.0,
                workflow_status=status
            )
            api_test_session.add(episode)
        api_test_session.commit()

        # Act - Filter by status
        response = api_client.get(
            "/api/v1/episodes",
            params={"status": WorkflowStatus.READY_FOR_REVIEW.value}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert all(e["workflow_status"] == WorkflowStatus.READY_FOR_REVIEW.value
                   for e in data["items"])

    @patch("app.api.episodes.get_llm_client")
    def test_trigger_workflow_schedules_background_task(self, mock_get_llm, api_client, api_test_session):
        """
        Behavior: Triggering workflow schedules background task

        Given:
            - An existing episode
        When:
            - POST /api/v1/episodes/{id}/run
        Then:
            - Returns 202 (accepted)
            - Background task is scheduled
        """
        # Arrange
        episode = Episode(
            title="Workflow Test",
            file_hash="workflow_hash",
            source_url="https://youtube.com/watch?v=workflow",
            duration=100.0,
            workflow_status=WorkflowStatus.READY_FOR_REVIEW.value
        )
        api_test_session.add(episode)
        api_test_session.commit()

        # Mock workflow runner to avoid actual execution
        with patch("app.api.episodes.WorkflowRunner") as mock_runner_class:
            mock_runner = Mock()
            mock_runner_class.return_value = mock_runner

            # Act
            response = api_client.post(
                f"/api/v1/episodes/{episode.id}/run",
                json={"force_restart": False}
            )

            # Assert
            assert response.status_code == 202
            data = response.json()
            assert data["id"] == episode.id
            assert "background" in data["message"].lower()


# =============================================================================
# Transcript and Translation API Workflow Tests
# =============================================================================

class TestTranscriptTranslationAPIWorkflow:
    """Transcript and Translation API end-to-end workflow tests."""

    def test_get_transcripts_with_translations(self, api_client, full_episode_with_content):
        """
        Behavior: Get transcripts with Chinese translations

        Given:
            - Episode with cues and translations
        When:
            - GET /api/v1/episodes/{id}/transcripts
        Then:
            - Returns cues with translations
        """
        # Act
        response = api_client.get(
            f"/api/v1/episodes/{full_episode_with_content.id}/transcripts"
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["episode_id"] == full_episode_with_content.id
        assert data["total"] == 6
        assert len(data["items"]) == 6

        # Verify first item has translation
        first_item = data["items"][0]
        assert "translation" in first_item
        assert first_item["translation"] is not None
        assert "这是测试句子" in first_item["translation"]

    def test_get_transcripts_filtered_by_chapter(self, api_client, full_episode_with_content, api_test_session):
        """
        Behavior: Get transcripts filtered by chapter

        Given:
            - Episode with multiple chapters
        When:
            - GET /api/v1/episodes/{id}/transcripts?chapter_id=X
        Then:
            - Returns only cues from specified chapter
        """
        # Arrange - Get first chapter ID
        chapter = api_test_session.query(Chapter).filter(
            Chapter.episode_id == full_episode_with_content.id
        ).first()

        # Act
        response = api_client.get(
            f"/api/v1/episodes/{full_episode_with_content.id}/transcripts",
            params={"chapter_id": chapter.id}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3

    def test_update_translation_sets_rlhf_flag(self, api_client, full_episode_with_content, api_test_session):
        """
        Behavior: Updating translation sets is_edited flag

        Given:
            - Translation with original value
        When:
            - PATCH /api/v1/translations/{id} with new translation
        Then:
            - Translation is updated
            - is_edited is set to True
        """
        # Arrange - Get first translation
        translation = api_test_session.query(Translation).first()
        original_text = translation.translation

        # Act
        response = api_client.patch(
            f"/api/v1/translations/{translation.id}",
            json={"translation": "用户手动修改的翻译内容"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["translation"] == "用户手动修改的翻译内容"
        assert data["is_edited"] is True

        # Verify in database
        api_test_session.refresh(translation)
        assert translation.translation == "用户手动修改的翻译内容"
        assert translation.is_edited is True
        assert translation.original_translation == original_text

    def test_get_effective_text_returns_corrected_text(self, api_client, api_test_session):
        """
        Behavior: Get effective text returns corrected text when available

        Given:
            - Cue with corrected_text
        When:
            - GET /api/v1/cues/{cue_id}/effective-text
        Then:
            - Returns corrected_text instead of original text
        """
        # Arrange - Create cue with corrected text
        episode = Episode(
            title="Effective Text Test",
            file_hash="effective_text_hash",
            source_url="https://youtube.com/watch?v=effective",
            duration=50.0
        )
        api_test_session.add(episode)
        api_test_session.flush()

        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=0,
            segment_id="segment_effective",
            start_time=0.0,
            end_time=50.0
        )
        api_test_session.add(segment)
        api_test_session.flush()

        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=0.0,
            end_time=5.0,
            text="Original text with error",
            corrected_text="Corrected text",
            is_corrected=True
        )
        api_test_session.add(cue)
        api_test_session.flush()

        # Act
        response = api_client.get(f"/api/v1/cues/{cue.id}/effective-text")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["cue_id"] == cue.id
        assert data["effective_text"] == "Corrected text"


# =============================================================================
# Chapter and Marketing API Workflow Tests
# =============================================================================

class TestChapterMarketingAPIWorkflow:
    """Chapter and Marketing API end-to-end workflow tests."""

    def test_get_chapters_with_details(self, api_client, full_episode_with_content):
        """
        Behavior: Get episode chapters with summary

        Given:
            - Episode with chapters
        When:
            - GET /api/v1/episodes/{id}/chapters
        Then:
            - Returns all chapters with details
        """
        # Act
        response = api_client.get(
            f"/api/v1/episodes/{full_episode_with_content.id}/chapters"
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

        # Verify chapter structure
        chapter = data[0]
        assert "id" in chapter
        assert "title" in chapter
        assert "summary" in chapter
        assert "start_time" in chapter
        assert "end_time" in chapter

    def test_get_chapter_cues(self, api_client, full_episode_with_content, api_test_session):
        """
        Behavior: Get cues for specific chapter

        Given:
            - Episode with chapters
        When:
            - GET /api/v1/chapters/{id}/cues
        Then:
            - Returns only cues from that chapter
        """
        # Arrange - Get first chapter
        chapter = api_test_session.query(Chapter).filter(
            Chapter.episode_id == full_episode_with_content.id
        ).first()

        # Act
        response = api_client.get(f"/api/v1/chapters/{chapter.id}/cues")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        assert all(c["chapter_id"] == chapter.id for c in data)

    @patch("app.api.marketing.get_llm_client")
    def test_generate_marketing_post_workflow(self, mock_get_llm, api_client, full_episode_with_content):
        """
        Behavior: Generate marketing post for episode

        Given:
            - Episode with content
        When:
            - POST /api/v1/episodes/{id}/marketing-posts/generate
        Then:
            - Creates marketing post
            - Returns created post
        """
        # Arrange - Mock LLM client
        mock_llm = Mock()
        mock_get_llm.return_value = mock_llm

        # Act
        response = api_client.post(
            f"/api/v1/episodes/{full_episode_with_content.id}/marketing-posts/generate"
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["platform"] == "xhs"
        assert data["angle_tag"] == "AI干货向"
        assert data["status"] == "pending"

    def test_list_marketing_posts(self, api_client, api_test_session, full_episode_with_content):
        """
        Behavior: List marketing posts for episode

        Given:
            - Episode with marketing posts
        When:
            - GET /api/v1/episodes/{id}/marketing-posts
        Then:
            - Returns all marketing posts
        """
        # Arrange - Create marketing posts
        post1 = MarketingPost(
            episode_id=full_episode_with_content.id,
            platform="xhs",
            angle_tag="干货硬核向",
            title="Test Title 1",
            content="Test content 1"
        )
        post2 = MarketingPost(
            episode_id=full_episode_with_content.id,
            platform="xhs",
            angle_tag="轻松有趣向",
            title="Test Title 2",
            content="Test content 2"
        )
        api_test_session.add(post1)
        api_test_session.add(post2)
        api_test_session.commit()

        # Act
        response = api_client.get(
            f"/api/v1/episodes/{full_episode_with_content.id}/marketing-posts"
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["angle_tag"] == "干货硬核向"
        assert data[1]["angle_tag"] == "轻松有趣向"


# =============================================================================
# Publication API Workflow Tests
# =============================================================================

class TestPublicationAPIWorkflow:
    """Publication API end-to-end workflow tests."""

    def test_get_publication_status(self, api_client, api_test_session, full_episode_with_content):
        """
        Behavior: Get publication status for episode

        Given:
            - Episode with publication records
        When:
            - GET /api/v1/episodes/{id}/publication-status
        Then:
            - Returns publication records and summary
        """
        # Arrange - Create publication records
        record_success = PublicationRecord(
            episode_id=full_episode_with_content.id,
            platform="feishu",
            status="success",
            platform_record_id="feishu_123"
        )
        record_failed = PublicationRecord(
            episode_id=full_episode_with_content.id,
            platform="ima",
            status="failed",
            error_message="API timeout"
        )
        api_test_session.add(record_success)
        api_test_session.add(record_failed)
        api_test_session.commit()

        # Act
        response = api_client.get(
            f"/api/v1/episodes/{full_episode_with_content.id}/publication-status"
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["episode_id"] == full_episode_with_content.id
        assert data["summary"]["total"] == 2
        assert data["summary"]["success"] == 1
        assert data["summary"]["failed"] == 1
        assert len(data["records"]) == 2

    @patch("app.api.publications.get_llm_client")
    def test_trigger_publish_workflow(self, mock_get_llm, api_client, api_test_session):
        """
        Behavior: Trigger publish workflow schedules background task

        Given:
            - Episode ready for publishing
        When:
            - POST /api/v1/episodes/{id}/publish
        Then:
            - Schedules background task
            - Returns 202 (accepted)
        """
        # Arrange - Create ready episode
        episode = Episode(
            title="Publish Test",
            file_hash="publish_test_hash",
            source_url="https://youtube.com/watch?v=publish_test",
            duration=100.0,
            workflow_status=WorkflowStatus.READY_FOR_REVIEW.value
        )
        api_test_session.add(episode)
        api_test_session.commit()

        # Mock workflow publisher
        with patch("app.api.publications.WorkflowPublisher") as mock_publisher_class:
            mock_publisher = Mock()
            mock_publisher_class.return_value = mock_publisher

            # Act
            response = api_client.post(f"/api/v1/episodes/{episode.id}/publish")

            # Assert
            assert response.status_code == 202
            data = response.json()
            assert data["id"] == episode.id
            assert "background" in data["message"].lower()

    def test_retry_failed_publication(self, api_client, api_test_session, full_episode_with_content):
        """
        Behavior: Retry failed publication record

        Given:
            - Failed publication record
        When:
            - POST /api/v1/publications/{id}/retry
        Then:
            - Schedules retry
            - Returns pending status
        """
        # Arrange - Create failed record
        record = PublicationRecord(
            episode_id=full_episode_with_content.id,
            platform="feishu",
            status="failed",
            error_message="Network error"
        )
        api_test_session.add(record)
        api_test_session.commit()

        # Mock workflow publisher
        with patch("app.api.publications.WorkflowPublisher") as mock_publisher_class:
            mock_publisher = Mock()

            # Act
            response = api_client.post(f"/api/v1/publications/{record.id}/retry")

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == record.id
            assert data["status"] == "pending"
            assert "retry" in data["message"].lower()

    def test_retry_already_succeeded_returns_message(self, api_client, api_test_session, full_episode_with_content):
        """
        Behavior: Retry already succeeded publication returns message

        Given:
            - Successful publication record
        When:
            - POST /api/v1/publications/{id}/retry
        Then:
            - Returns message (no retry needed)
        """
        # Arrange - Create successful record
        record = PublicationRecord(
            episode_id=full_episode_with_content.id,
            platform="feishu",
            status="success",
            platform_record_id="feishu_123"
        )
        api_test_session.add(record)
        api_test_session.commit()

        # Act
        response = api_client.post(f"/api/v1/publications/{record.id}/retry")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "no need to retry" in data["message"].lower()


# =============================================================================
# Cross-Module Integration Tests
# =============================================================================

class TestCrossModuleIntegration:
    """Tests spanning multiple API modules."""

    def test_full_episode_lifecycle_workflow(self, api_client, api_test_session):
        """
        Behavior: Complete episode lifecycle from creation to publication

        Given:
            - Empty database
        When:
            1. Create episode
            2. Add content (manually for testing)
            3. Query transcripts
            4. Update translation
            5. Get chapters
            6. Generate marketing post
            7. Query publication status
        Then:
            - All operations succeed
            - Data remains consistent
        """
        # Step 1: Create episode
        create_response = api_client.post(
            "/api/v1/episodes",
            json={"url": "https://youtube.com/watch?v=lifecycle_test"}
        )
        assert create_response.status_code == 201
        episode_id = create_response.json()["id"]

        # Step 2: Add content (manually for testing)
        episode = api_test_session.get(Episode, episode_id)
        episode.workflow_status = WorkflowStatus.TRANSLATED.value
        api_test_session.flush()

        segment = AudioSegment(
            episode_id=episode_id,
            segment_index=0,
            segment_id="segment_lifecycle",
            start_time=0.0,
            end_time=60.0
        )
        api_test_session.add(segment)
        api_test_session.flush()

        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=0.0,
            end_time=5.0,
            text="Test sentence for lifecycle"
        )
        api_test_session.add(cue)
        api_test_session.flush()

        translation = Translation(
            cue_id=cue.id,
            language_code="zh",
            translation="生命周期测试翻译",
            original_translation="生命周期测试翻译"
        )
        api_test_session.add(translation)

        chapter = Chapter(
            episode_id=episode_id,
            chapter_index=0,
            title="Chapter 1",
            summary="Test chapter",
            start_time=0.0,
            end_time=60.0
        )
        api_test_session.add(chapter)
        api_test_session.commit()

        # Step 3: Query transcripts
        transcript_response = api_client.get(f"/api/v1/episodes/{episode_id}/transcripts")
        assert transcript_response.status_code == 200
        assert transcript_response.json()["total"] == 1

        # Step 4: Update translation
        translation = api_test_session.query(Translation).first()
        update_response = api_client.patch(
            f"/api/v1/translations/{translation.id}",
            json={"translation": "修改后的翻译"}
        )
        assert update_response.status_code == 200
        assert update_response.json()["is_edited"] is True

        # Step 5: Get chapters
        chapter_response = api_client.get(f"/api/v1/episodes/{episode_id}/chapters")
        assert chapter_response.status_code == 200
        assert len(chapter_response.json()) == 1

        # Step 6: Generate marketing post (with mocked LLM)
        with patch("app.api.marketing.get_llm_client") as mock_get_llm:
            mock_llm = Mock()
            mock_get_llm.return_value = Mock()

            marketing_response = api_client.post(
                f"/api/v1/episodes/{episode_id}/marketing-posts/generate"
            )
            assert marketing_response.status_code == 201

        # Step 7: Query publication status
        status_response = api_client.get(
            f"/api/v1/episodes/{episode_id}/publication-status"
        )
        assert status_response.status_code == 200
        assert status_response.json()["summary"]["total"] == 0
