"""
Unit tests for AudioSegment model.

Test Naming Convention (BDD):
- test_<behavior>_<expected_result>
"""
import pytest

from sqlalchemy.exc import IntegrityError

from app.enums.transcription_status import TranscriptionStatus
from app.models.audio_segment import AudioSegment
from app.models.episode import Episode


class TestAudioSegmentCreate:
    """Test AudioSegment creation."""

    def test_audio_segment_create_minimal_fields(self, test_session):
        """Given: Database session, episode, and required fields
        When: Creating AudioSegment with minimal fields
        Then: AudioSegment is created with correct defaults
        """
        # Create episode first
        episode = Episode(
            title="Test Episode",
            file_hash="abc123",
            duration=180.0,
        )
        test_session.add(episode)
        test_session.flush()

        # Create audio segment
        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=0,
            segment_id="segment_001",
            start_time=0.0,
            end_time=30.0,
        )
        test_session.add(segment)
        test_session.flush()

        assert segment.id is not None
        assert segment.episode_id == episode.id
        assert segment.segment_index == 0
        assert segment.segment_id == "segment_001"
        assert segment.start_time == 0.0
        assert segment.end_time == 30.0
        assert segment.status == TranscriptionStatus.PENDING.value
        assert segment.segment_path is None
        assert segment.error_message is None
        assert segment.retry_count == 0

    def test_audio_segment_create_full_fields(self, test_session):
        """Given: Database session and episode
        When: Creating AudioSegment with all fields
        Then: All field values are correctly set
        """
        episode = Episode(
            title="Test Episode",
            file_hash="xyz789",
            duration=300.0,
        )
        test_session.add(episode)
        test_session.flush()

        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=1,
            segment_id="segment_002",
            segment_path="/tmp/segment_002.mp3",
            start_time=30.0,
            end_time=60.0,
            status=TranscriptionStatus.PROCESSING.value,
            error_message="Test error",
            retry_count=2,
        )
        test_session.add(segment)
        test_session.flush()

        assert segment.episode_id == episode.id
        assert segment.segment_index == 1
        assert segment.segment_id == "segment_002"
        assert segment.segment_path == "/tmp/segment_002.mp3"
        assert segment.start_time == 30.0
        assert segment.end_time == 60.0
        assert segment.status == TranscriptionStatus.PROCESSING.value
        assert segment.error_message == "Test error"
        assert segment.retry_count == 2

    def test_audio_segment_status_default_is_pending(self, test_session):
        """Given: New AudioSegment
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

        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=0,
            segment_id="seg_001",
            start_time=0.0,
            end_time=10.0,
        )
        test_session.add(segment)
        test_session.flush()

        assert segment.status == TranscriptionStatus.PENDING.value

    def test_audio_segment_retry_count_default_is_zero(self, test_session):
        """Given: New AudioSegment
        When: Not specifying retry_count
        Then: Defaults to 0
        """
        episode = Episode(
            title="Test Episode",
            file_hash="test123",
            duration=100.0,
        )
        test_session.add(episode)
        test_session.flush()

        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=0,
            segment_id="seg_001",
            start_time=0.0,
            end_time=10.0,
        )
        test_session.add(segment)
        test_session.flush()

        assert segment.retry_count == 0


class TestAudioSegmentConstraints:
    """Test AudioSegment database constraints."""

    def test_audio_segment_episode_id_not_null_constraint(self, test_session):
        """Given: AudioSegment without episode_id
        When: Attempting to save
        Then: Raises IntegrityError
        """
        segment = AudioSegment(
            # episode_id is missing
            segment_index=0,
            segment_id="seg_001",
            start_time=0.0,
            end_time=10.0,
        )
        test_session.add(segment)

        with pytest.raises(IntegrityError):
            test_session.flush()

    def test_audio_segment_segment_index_not_null_constraint(self, test_session):
        """Given: AudioSegment without segment_index
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

        segment = AudioSegment(
            episode_id=episode.id,
            # segment_index is missing
            segment_id="seg_001",
            start_time=0.0,
            end_time=10.0,
        )
        test_session.add(segment)

        with pytest.raises(IntegrityError):
            test_session.flush()

    def test_audio_segment_segment_id_not_null_constraint(self, test_session):
        """Given: AudioSegment without segment_id
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

        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=0,
            # segment_id is missing
            start_time=0.0,
            end_time=10.0,
        )
        test_session.add(segment)

        with pytest.raises(IntegrityError):
            test_session.flush()

    def test_audio_segment_start_time_not_null_constraint(self, test_session):
        """Given: AudioSegment without start_time
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

        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=0,
            segment_id="seg_001",
            # start_time is missing
            end_time=10.0,
        )
        test_session.add(segment)

        with pytest.raises(IntegrityError):
            test_session.flush()

    def test_audio_segment_end_time_not_null_constraint(self, test_session):
        """Given: AudioSegment without end_time
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

        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=0,
            segment_id="seg_001",
            start_time=0.0,
            # end_time is missing
        )
        test_session.add(segment)

        with pytest.raises(IntegrityError):
            test_session.flush()

    def test_audio_segment_unique_constraint_episode_id_segment_index(self, test_session):
        """Given: Episode with existing segment at index 0
        When: Creating another segment with same episode_id and segment_index
        Then: Raises IntegrityError
        """
        episode = Episode(
            title="Test Episode",
            file_hash="test123",
            duration=100.0,
        )
        test_session.add(episode)
        test_session.flush()

        # Create first segment
        segment1 = AudioSegment(
            episode_id=episode.id,
            segment_index=0,
            segment_id="segment_001",
            start_time=0.0,
            end_time=30.0,
        )
        test_session.add(segment1)
        test_session.flush()

        # Try to create duplicate
        segment2 = AudioSegment(
            episode_id=episode.id,
            segment_index=0,  # Same index
            segment_id="segment_002",
            start_time=30.0,
            end_time=60.0,
        )
        test_session.add(segment2)

        with pytest.raises(IntegrityError):
            test_session.flush()

    def test_audio_segment_different_episodes_same_index_allowed(self, test_session):
        """Given: Two different episodes
        When: Creating segments with same segment_index for each episode
        Then: Both segments are created successfully
        """
        episode1 = Episode(
            title="Episode 1",
            file_hash="hash1",
            duration=100.0,
        )
        episode2 = Episode(
            title="Episode 2",
            file_hash="hash2",
            duration=100.0,
        )
        test_session.add(episode1)
        test_session.add(episode2)
        test_session.flush()

        # Both segments can have index 0 because they belong to different episodes
        segment1 = AudioSegment(
            episode_id=episode1.id,
            segment_index=0,
            segment_id="segment_001",
            start_time=0.0,
            end_time=30.0,
        )
        segment2 = AudioSegment(
            episode_id=episode2.id,
            segment_index=0,
            segment_id="segment_002",
            start_time=0.0,
            end_time=30.0,
        )
        test_session.add(segment1)
        test_session.add(segment2)
        test_session.flush()

        assert segment1.id is not None
        assert segment2.id is not None


class TestAudioSegmentProperties:
    """Test AudioSegment properties."""

    def test_audio_segment_duration_property(self, test_session):
        """Given: AudioSegment with start_time and end_time
        When: Accessing duration property
        Then: Returns correct duration (end_time - start_time)
        """
        episode = Episode(
            title="Test Episode",
            file_hash="test123",
            duration=100.0,
        )
        test_session.add(episode)
        test_session.flush()

        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=0,
            segment_id="seg_001",
            start_time=10.5,
            end_time=45.5,
        )
        test_session.add(segment)
        test_session.flush()

        assert segment.duration == 35.0


class TestAudioSegmentRelationships:
    """Test AudioSegment relationships."""

    def test_audio_segment_belongs_to_episode(self, test_session):
        """Given: AudioSegment with episode_id
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

        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=0,
            segment_id="seg_001",
            start_time=0.0,
            end_time=30.0,
        )
        test_session.add(segment)
        test_session.flush()

        # Refresh to load relationship
        test_session.refresh(segment)
        test_session.refresh(episode)

        assert segment.episode.id == episode.id
        assert segment.episode.title == "Test Episode"


class TestAudioSegmentRepr:
    """Test AudioSegment __repr__ method."""

    def test_audio_segment_repr_contains_id_and_segment_id(self, test_session):
        """Given: AudioSegment object
        When: Calling repr()
        Then: Returns string with id and segment_id
        """
        episode = Episode(
            title="Test Episode",
            file_hash="test123",
            duration=100.0,
        )
        test_session.add(episode)
        test_session.flush()

        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=0,
            segment_id="segment_001",
            start_time=0.0,
            end_time=30.0,
        )
        test_session.add(segment)
        test_session.flush()

        result = repr(segment)

        assert "AudioSegment" in result
        assert f"id={segment.id}" in result
        assert "segment_001" in result
        assert "pending" in result
