"""
Unit tests for Episode model.

Test Naming Convention (BDD):
- test_<behavior>_<expected_result>
"""
import pytest

from sqlalchemy.exc import IntegrityError

from app.enums.workflow_status import WorkflowStatus
from app.models.episode import Episode


class TestEpisodeCreate:
    """Test Episode creation."""

    def test_episode_create_minimal_fields(self, test_session):
        """Given: Database session and required fields
        When: Creating Episode with minimal fields
        Then: Episode is created with correct defaults
        """
        episode = Episode(
            title="Test Episode",
            file_hash="abc123",
            duration=180.0,
        )
        test_session.add(episode)
        test_session.flush()

        assert episode.id is not None
        assert episode.title == "Test Episode"
        assert episode.file_hash == "abc123"
        assert episode.duration == 180.0
        assert episode.language == "en-US"  # Default value
        assert episode.workflow_status == WorkflowStatus.INIT.value  # Default value

    def test_episode_create_full_fields(self, test_session):
        """Given: Database session
        When: Creating Episode with all fields
        Then: All field values are correctly set
        """
        episode = Episode(
            title="Full Episode",
            show_name="Test Show",
            source_url="https://example.com/video",
            audio_path="/path/to/audio.mp3",
            file_hash="xyz789",
            file_size=1024000,
            duration=300.5,
            language="zh-CN",
            ai_summary="Test summary",
            workflow_status=WorkflowStatus.DOWNLOADED.value,
        )
        test_session.add(episode)
        test_session.flush()

        assert episode.title == "Full Episode"
        assert episode.show_name == "Test Show"
        assert episode.source_url == "https://example.com/video"
        assert episode.audio_path == "/path/to/audio.mp3"
        assert episode.file_hash == "xyz789"
        assert episode.file_size == 1024000
        assert episode.duration == 300.5
        assert episode.language == "zh-CN"
        assert episode.ai_summary == "Test summary"
        assert episode.workflow_status == WorkflowStatus.DOWNLOADED.value

    def test_episode_workflow_status_default_is_init(self, test_session):
        """Given: New Episode
        When: Not specifying workflow_status
        Then: Defaults to INIT (0)
        """
        episode = Episode(
            title="Test",
            file_hash="test123",
            duration=100.0,
        )
        test_session.add(episode)
        test_session.flush()

        assert episode.workflow_status == WorkflowStatus.INIT.value

    def test_episode_language_default_is_en_us(self, test_session):
        """Given: New Episode
        When: Not specifying language
        Then: Defaults to 'en-US'
        """
        episode = Episode(
            title="Test",
            file_hash="test123",
            duration=100.0,
        )
        test_session.add(episode)
        test_session.flush()

        assert episode.language == "en-US"


class TestEpisodeConstraints:
    """Test Episode database constraints."""

    def test_episode_file_hash_unique_constraint(self, test_session):
        """Given: Episode with existing file_hash
        When: Creating another Episode with same file_hash
        Then: Raises IntegrityError
        """
        # Create first episode
        episode1 = Episode(
            title="Episode 1",
            file_hash="duplicate_hash",
            duration=100.0,
        )
        test_session.add(episode1)
        test_session.flush()

        # Try to create duplicate
        episode2 = Episode(
            title="Episode 2",
            file_hash="duplicate_hash",  # Same hash
            duration=200.0,
        )
        test_session.add(episode2)

        with pytest.raises(IntegrityError):
            test_session.flush()

    def test_episode_title_not_null_constraint(self, test_session):
        """Given: Episode without title
        When: Attempting to save
        Then: Raises IntegrityError
        """
        episode = Episode(
            # title is missing
            file_hash="test_title_missing",
            duration=100.0,
        )
        test_session.add(episode)

        with pytest.raises(IntegrityError):
            test_session.flush()

    def test_episode_file_hash_not_null_constraint(self, test_session):
        """Given: Episode without file_hash
        When: Attempting to save
        Then: Raises error
        """
        episode = Episode(
            title="Test",
            # file_hash is missing
            duration=100.0,
        )
        test_session.add(episode)

        with pytest.raises(IntegrityError):
            test_session.flush()

    def test_episode_duration_not_null_constraint(self, test_session):
        """Given: Episode without duration
        When: Attempting to save
        Then: Raises error
        """
        episode = Episode(
            title="Test",
            file_hash="test_duration_missing",
            # duration is missing
        )
        test_session.add(episode)

        with pytest.raises(IntegrityError):
            test_session.flush()


class TestEpisodeTimestamps:
    """Test TimestampMixin on Episode."""

    def test_episode_created_at_is_set(self, test_session):
        """Given: New Episode
        When: Saving to database
        Then: created_at is automatically set
        """
        from datetime import datetime

        episode = Episode(
            title="Test",
            file_hash="test123",
            duration=100.0,
        )
        test_session.add(episode)
        test_session.flush()

        assert episode.created_at is not None
        assert isinstance(episode.created_at, datetime)

    def test_episode_updated_at_is_set(self, test_session):
        """Given: New Episode
        When: Saving to database
        Then: updated_at is automatically set
        """
        from datetime import datetime

        episode = Episode(
            title="Test",
            file_hash="test123",
            duration=100.0,
        )
        test_session.add(episode)
        test_session.flush()

        assert episode.updated_at is not None
        assert isinstance(episode.updated_at, datetime)


class TestEpisodeRepr:
    """Test Episode __repr__ method."""

    def test_episode_repr_contains_id_and_title(self, test_session):
        """Given: Episode object
        When: Calling repr()
        Then: Returns string with id and title
        """
        episode = Episode(
            title="Test Episode",
            file_hash="test123",
            duration=100.0,
            workflow_status=0,
        )
        test_session.add(episode)
        test_session.flush()

        result = repr(episode)

        assert "Episode" in result
        assert f"id={episode.id}" in result
        assert "Test Episode" in result
        assert "status=0" in result


class TestEpisodeProofreadFields:
    """Test Episode proofreading-related fields."""

    def test_proofread_status_default_is_pending(self, test_session):
        """Given: New Episode
        When: Not specifying proofread_status
        Then: Defaults to 'pending'
        """
        episode = Episode(
            title="Test",
            file_hash="test123",
            duration=100.0,
        )
        test_session.add(episode)
        test_session.flush()

        assert episode.proofread_status == "pending"

    def test_proofread_at_nullable(self, test_session):
        """Given: New Episode
        When: Not specifying proofread_at
        Then: Can be NULL
        """
        episode = Episode(
            title="Test",
            file_hash="test123",
            duration=100.0,
        )
        test_session.add(episode)
        test_session.flush()

        assert episode.proofread_at is None

    def test_proofread_at_can_be_set(self, test_session):
        """Given: Episode
        When: Setting proofread_at
        Then: Value is correctly saved
        """
        from datetime import datetime

        episode = Episode(
            title="Test",
            file_hash="test123",
            duration=100.0,
        )
        test_session.add(episode)
        test_session.flush()

        episode.proofread_at = datetime(2026, 2, 5, 12, 0, 0)
        test_session.commit()

        assert episode.proofread_at is not None
        assert episode.proofread_at.hour == 12
