"""
Unit tests for PublicationRecord model.

Test Naming Convention (BDD):
- test_<behavior>_<expected_result>
"""
import pytest

from sqlalchemy.exc import IntegrityError

from app.models.publication_record import PublicationRecord
from app.models.episode import Episode


class TestPublicationRecordCreate:
    """Test PublicationRecord creation."""

    def test_publication_record_create_minimal_fields(self, test_session):
        """Given: Database session and episode
        When: Creating PublicationRecord with minimal fields
        Then: PublicationRecord is created with correct defaults
        """
        episode = Episode(
            title="Test Episode",
            file_hash="abc123",
            duration=180.0,
        )
        test_session.add(episode)
        test_session.flush()

        record = PublicationRecord(
            episode_id=episode.id,
            platform="feishu",
        )
        test_session.add(record)
        test_session.flush()

        assert record.id is not None
        assert record.episode_id == episode.id
        assert record.platform == "feishu"
        assert record.platform_record_id is None
        assert record.status == "pending"  # Default value
        assert record.published_at is None
        assert record.error_message is None

    def test_publication_record_create_full_fields(self, test_session):
        """Given: Database session and episode
        When: Creating PublicationRecord with all fields
        Then: All field values are correctly set
        """
        episode = Episode(
            title="Test Episode",
            file_hash="xyz789",
            duration=300.0,
        )
        test_session.add(episode)
        test_session.flush()

        record = PublicationRecord(
            episode_id=episode.id,
            platform="ima",
            platform_record_id="rec_12345",
            status="success",
            error_message="Test error",
        )
        test_session.add(record)
        test_session.flush()

        assert record.episode_id == episode.id
        assert record.platform == "ima"
        assert record.platform_record_id == "rec_12345"
        assert record.status == "success"
        assert record.error_message == "Test error"

    def test_publication_record_status_default_is_pending(self, test_session):
        """Given: New PublicationRecord
        When: Not specifying status
        Then: Defaults to 'pending'
        """
        episode = Episode(
            title="Test Episode",
            file_hash="test123",
            duration=100.0,
        )
        test_session.add(episode)
        test_session.flush()

        record = PublicationRecord(
            episode_id=episode.id,
            platform="feishu",
        )
        test_session.add(record)
        test_session.flush()

        assert record.status == "pending"


class TestPublicationRecordConstraints:
    """Test PublicationRecord database constraints."""

    def test_publication_record_episode_id_not_null_constraint(self, test_session):
        """Given: PublicationRecord without episode_id
        When: Attempting to save
        Then: Raises IntegrityError
        """
        record = PublicationRecord(
            # episode_id is missing
            platform="feishu",
        )
        test_session.add(record)

        with pytest.raises(IntegrityError):
            test_session.flush()

    def test_publication_record_platform_not_null_constraint(self, test_session):
        """Given: PublicationRecord without platform
        When: Attempting to save
        Then: Raises error
        """
        episode = Episode(
            title="Test Episode",
            file_hash="test123",
            duration=100.0,
        )
        test_session.add(episode)
        test_session.flush()

        record = PublicationRecord(
            episode_id=episode.id,
            # platform is missing
        )
        test_session.add(record)

        with pytest.raises(IntegrityError):
            test_session.flush()

    def test_publication_record_no_unique_constraint_allows_duplicates(self, test_session):
        """Given: Episode with existing publication record for platform
        When: Creating another record with same episode_id and platform
        Then: Both records are created (allows retry history)
        """
        episode = Episode(
            title="Test Episode",
            file_hash="test123",
            duration=100.0,
        )
        test_session.add(episode)
        test_session.flush()

        # Create first record (failed)
        record1 = PublicationRecord(
            episode_id=episode.id,
            platform="feishu",
            status="failed",
            error_message="First attempt failed",
        )
        # Create second record (retry)
        record2 = PublicationRecord(
            episode_id=episode.id,
            platform="feishu",  # Same platform
            status="success",
        )
        test_session.add(record1)
        test_session.add(record2)
        test_session.flush()

        assert record1.id is not None
        assert record2.id is not None
        assert record1.id != record2.id  # Different records for retry history


class TestPublicationRecordRelationships:
    """Test PublicationRecord relationships."""

    def test_publication_record_belongs_to_episode(self, test_session):
        """Given: PublicationRecord with episode_id
        When: Accessing episode relationship
        Then: Returns correct Episode object
        """
        episode = Episode(
            title="Test Episode",
            file_hash="test123",
            duration=100.0,
        )
        test_session.add(episode)
        test_session.flush()

        record = PublicationRecord(
            episode_id=episode.id,
            platform="feishu",
        )
        test_session.add(record)
        test_session.flush()

        # Refresh to load relationship
        test_session.refresh(record)
        test_session.refresh(episode)

        assert record.episode.id == episode.id
        assert record.episode.title == "Test Episode"


class TestPublicationRecordRepr:
    """Test PublicationRecord __repr__ method."""

    def test_publication_record_repr_contains_id_and_platform(self, test_session):
        """Given: PublicationRecord object
        When: Calling repr()
        Then: Returns string with id and platform
        """
        episode = Episode(
            title="Test Episode",
            file_hash="test123",
            duration=100.0,
        )
        test_session.add(episode)
        test_session.flush()

        record = PublicationRecord(
            episode_id=episode.id,
            platform="feishu",
        )
        test_session.add(record)
        test_session.flush()

        result = repr(record)

        assert "PublicationRecord" in result
        assert f"id={record.id}" in result
        assert "feishu" in result
        assert "pending" in result
