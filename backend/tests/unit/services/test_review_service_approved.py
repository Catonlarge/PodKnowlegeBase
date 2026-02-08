"""
Unit tests for ReviewService - APPROVED status workflow.

Test Naming Convention (BDD):
- test_<behavior>_<expected_result>
"""
import pytest
import tempfile
from pathlib import Path
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import Episode, AudioSegment, TranscriptCue, Translation
from app.services.review_service import ReviewService
from app.enums.workflow_status import WorkflowStatus
from app.services.obsidian_service import ObsidianService


@pytest.fixture(scope="function")
def test_session():
    """Create a test database session."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False}
    )
    from app.models import Base
    Base.metadata.create_all(engine)

    SessionFactory = sessionmaker(bind=engine)
    session = SessionFactory()

    yield session

    session.close()


class TestReviewServiceApprovedWorkflow:
    """Test ReviewService APPROVED status workflow."""

    def test_sync_approved_episodes_updates_status_to_approved(self, test_session):
        """Given: Episode with READY_FOR_REVIEW status and Obsidian file with status: approved
        When: Calling sync_approved_episodes()
        Then: Episode status is updated to APPROVED
        """
        # Arrange
        episode = Episode(
            title="Test Episode",
            source_url="https://test.com/audio",
            file_hash="test_hash_123",
            duration=1800.0,
            workflow_status=WorkflowStatus.READY_FOR_REVIEW.value
        )
        test_session.add(episode)
        test_session.flush()

        # Create audio segment and transcript cue (required for ObsidianService)
        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=0,
            segment_id="segment_001",
            start_time=0.0,
            end_time=1800.0
        )
        test_session.add(segment)
        test_session.flush()

        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=0.0,
            end_time=5.0,
            speaker="SPEAKER_01",
            text="Test English text."
        )
        test_session.add(cue)
        test_session.flush()

        # Create translation
        translation = Translation(
            cue_id=cue.id,
            language_code="zh",
            translation="原始翻译",
            translation_status="completed"
        )
        test_session.add(translation)
        test_session.commit()

        # Create temp Obsidian directory
        with tempfile.TemporaryDirectory() as temp_dir:
            obsidian_dir = Path(temp_dir) / "obsidian" / "episodes"
            obsidian_dir.mkdir(parents=True, exist_ok=True)

            # Create ReviewService with custom notes_dir
            from unittest.mock import Mock
            review_service = ReviewService(test_session)
            review_service.notes_dir = obsidian_dir

            obsidian_file = obsidian_dir / f"{episode.id}-test-episode.md"
            obsidian_content = f"""---
task_id: {episode.id}
url: https://test.com/audio
status: approved
---

# Test Content

## 开场

**SPEAKER_01**

[00:00](cue://{cue.id}) Test English text.

原始翻译
"""
            obsidian_file.write_text(obsidian_content, encoding='utf-8')

            # Act
            count = review_service.sync_approved_episodes()

            # Assert
            assert count == 1
            test_session.expire_all()
            updated_episode = test_session.get(Episode, episode.id)
            assert updated_episode.workflow_status == WorkflowStatus.APPROVED.value

    def test_sync_approved_episodes_only_allows_from_ready_for_review(self, test_session):
        """Given: Episode with TRANSLATED status (not READY_FOR_REVIEW)
        When: Calling sync_approved_episodes()
        Then: Status is not updated (returns 0)
        """
        # Arrange
        episode = Episode(
            title="Test Episode",
            source_url="https://test.com/audio",
            file_hash="test_hash_123",
            duration=1800.0,
            workflow_status=WorkflowStatus.TRANSLATED.value
        )
        test_session.add(episode)
        test_session.flush()

        # Create temp Obsidian directory
        with tempfile.TemporaryDirectory() as temp_dir:
            obsidian_dir = Path(temp_dir) / "obsidian" / "episodes"
            obsidian_dir.mkdir(parents=True, exist_ok=True)

            obsidian_file = obsidian_dir / f"{episode.id}-test-episode.md"
            obsidian_content = f"""---
task_id: {episode.id}
url: https://test.com/audio
status: approved
---

# Test Content
"""
            obsidian_file.write_text(obsidian_content, encoding='utf-8')

            review_service = ReviewService(test_session)
            review_service.notes_dir = obsidian_dir

        # Act
        count = review_service.sync_approved_episodes()

        # Assert
        assert count == 0
        test_session.expire_all()
        updated_episode = test_session.get(Episode, episode.id)
        assert updated_episode.workflow_status == WorkflowStatus.TRANSLATED.value

    def test_sync_approved_episodes_handles_missing_obsidian_file(self, test_session):
        """Given: Episode with READY_FOR_REVIEW status but no Obsidian file
        When: Calling sync_approved_episodes()
        Then: Episode status is not updated
        """
        # Arrange
        episode = Episode(
            title="Test Episode",
            source_url="https://test.com/audio",
            file_hash="test_hash_123",
            duration=1800.0,
            workflow_status=WorkflowStatus.READY_FOR_REVIEW.value
        )
        test_session.add(episode)
        test_session.flush()

        review_service = ReviewService(test_session)

        # Act
        count = review_service.sync_approved_episodes()

        # Assert
        assert count == 0
        test_session.expire_all()
        updated_episode = test_session.get(Episode, episode.id)
        assert updated_episode.workflow_status == WorkflowStatus.READY_FOR_REVIEW.value

    def test_scan_review_status_detects_approved_status(self, test_session):
        """Given: Obsidian directory with files having different statuses
        When: Calling scan_review_status()
        Then: Returns correct status for each file
        """
        # Arrange
        with tempfile.TemporaryDirectory() as temp_dir:
            obsidian_dir = Path(temp_dir) / "obsidian" / "episodes"
            obsidian_dir.mkdir(parents=True, exist_ok=True)

            # Create episode 1 with approved status
            episode1 = Episode(
                title="Episode 1",
                source_url="https://test.com/1",
                file_hash="hash1",
                duration=100.0
            )
            test_session.add(episode1)
            test_session.flush()

            obsidian_file1 = obsidian_dir / "1-episode-1.md"
            obsidian_file1.write_text(
                "---\ntask_id: 1\nstatus: approved\n---\n", encoding='utf-8'
            )

            # Create episode 2 with pending_review status
            episode2 = Episode(
                title="Episode 2",
                source_url="https://test.com/2",
                file_hash="hash2",
                duration=200.0
            )
            test_session.add(episode2)
            test_session.flush()

            obsidian_file2 = obsidian_dir / "2-episode-2.md"
            obsidian_file2.write_text(
                "---\ntask_id: 2\nstatus: pending_review\n---\n", encoding='utf-8'
            )

            review_service = ReviewService(test_session)
            review_service.notes_dir = obsidian_dir

            # Act
            statuses = review_service.scan_review_status()

            # Assert
            assert len(statuses) == 2
            approved_status = [s for s in statuses if s.status == "approved"]
            pending_status = [s for s in statuses if s.status == "pending_review"]
            assert len(approved_status) == 1
            assert approved_status[0].episode_id == 1
            assert len(pending_status) == 1
            assert pending_status[0].episode_id == 2

    def test_check_episode_approved_returns_true_for_approved_status(self, test_session):
        """Given: Episode with Obsidian file containing status: approved
        When: Calling check_episode_approved()
        Then: Returns True
        """
        # Arrange
        episode = Episode(
            title="Test Episode",
            source_url="https://test.com/audio",
            file_hash="test_hash_123",
            duration=1800.0,
            workflow_status=WorkflowStatus.APPROVED.value
        )
        test_session.add(episode)
        test_session.flush()

        # Create temp Obsidian directory with approved status file
        with tempfile.TemporaryDirectory() as temp_dir:
            obsidian_dir = Path(temp_dir) / "obsidian" / "episodes"
            obsidian_dir.mkdir(parents=True, exist_ok=True)

            obsidian_file = obsidian_dir / f"{episode.id}-test-episode.md"
            obsidian_content = f"""---
task_id: {episode.id}
url: https://test.com/audio
status: approved
---

# Test Content
"""
            obsidian_file.write_text(obsidian_content, encoding='utf-8')

            review_service = ReviewService(test_session)
            review_service.notes_dir = obsidian_dir

            # Act
            result = review_service.check_episode_approved(episode.id)

            # Assert
            assert result is True

    def test_check_episode_approved_returns_false_for_non_approved_status(self, test_session):
        """Given: Episode with Obsidian file containing status: pending_review
        When: Calling check_episode_approved()
        Then: Returns False
        """
        # Arrange
        episode = Episode(
            title="Test Episode",
            source_url="https://test.com/audio",
            file_hash="test_hash_123",
            duration=1800.0,
            workflow_status=WorkflowStatus.READY_FOR_REVIEW.value
        )
        test_session.add(episode)
        test_session.flush()

        # Create temp Obsidian directory with pending_review status file
        with tempfile.TemporaryDirectory() as temp_dir:
            obsidian_dir = Path(temp_dir) / "obsidian" / "episodes"
            obsidian_dir.mkdir(parents=True, exist_ok=True)

            obsidian_file = obsidian_dir / f"{episode.id}-test-episode.md"
            obsidian_content = f"""---
task_id: {episode.id}
url: https://test.com/audio
status: pending_review
---

# Test Content
"""
            obsidian_file.write_text(obsidian_content, encoding='utf-8')

            review_service = ReviewService(test_session)
            review_service.notes_dir = obsidian_dir

            # Act
            result = review_service.check_episode_approved(episode.id)

            # Assert
            assert result is False
