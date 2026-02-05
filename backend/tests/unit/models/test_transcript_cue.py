"""
Unit tests for TranscriptCue model.

Test Naming Convention (BDD):
- test_<behavior>_<expected_result>
"""
import pytest

from sqlalchemy.exc import IntegrityError

from app.models.transcript_cue import TranscriptCue
from app.models.audio_segment import AudioSegment
from app.models.episode import Episode


class TestTranscriptCueCreate:
    """Test TranscriptCue creation."""

    def test_transcript_cue_create_minimal_fields(self, test_session):
        """Given: Database session and segment
        When: Creating TranscriptCue with minimal fields
        Then: TranscriptCue is created with correct defaults
        """
        # Create episode and segment first
        episode = Episode(
            title="Test Episode",
            file_hash="abc123",
            duration=180.0,
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

        # Create transcript cue
        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=0.5,
            end_time=3.5,
            text="Hello world.",
        )
        test_session.add(cue)
        test_session.flush()

        assert cue.id is not None
        assert cue.segment_id == segment.id
        assert cue.start_time == 0.5
        assert cue.end_time == 3.5
        assert cue.text == "Hello world."
        assert cue.speaker == "Unknown"  # Default value

    def test_transcript_cue_create_full_fields(self, test_session):
        """Given: Database session and segment
        When: Creating TranscriptCue with all fields
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
            segment_index=0,
            segment_id="segment_001",
            start_time=0.0,
            end_time=30.0,
        )
        test_session.add(segment)
        test_session.flush()

        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=5.0,
            end_time=8.0,
            speaker="Speaker A",
            text="This is a test.",
        )
        test_session.add(cue)
        test_session.flush()

        assert cue.segment_id == segment.id
        assert cue.start_time == 5.0
        assert cue.end_time == 8.0
        assert cue.speaker == "Speaker A"
        assert cue.text == "This is a test."

    def test_transcript_cue_speaker_default_is_unknown(self, test_session):
        """Given: New TranscriptCue
        When: Not specifying speaker
        Then: Defaults to 'Unknown'
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

        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=0.0,
            end_time=3.0,
            text="Test text",
        )
        test_session.add(cue)
        test_session.flush()

        assert cue.speaker == "Unknown"


class TestTranscriptCueConstraints:
    """Test TranscriptCue database constraints."""

    def test_transcript_cue_segment_id_nullable(self, test_session):
        """Given: TranscriptCue without segment_id
        When: Creating and saving
        Then: Segment can be created with NULL segment_id (flexible design)
        """
        cue = TranscriptCue(
            # segment_id is nullable
            segment_id=None,
            start_time=0.0,
            end_time=3.0,
            text="Test text",
        )
        test_session.add(cue)
        test_session.flush()

        assert cue.id is not None
        assert cue.segment_id is None

    def test_transcript_cue_start_time_not_null_constraint(self, test_session):
        """Given: TranscriptCue without start_time
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
            segment_id="segment_001",
            start_time=0.0,
            end_time=30.0,
        )
        test_session.add(segment)
        test_session.flush()

        cue = TranscriptCue(
            segment_id=segment.id,
            # start_time is missing
            end_time=3.0,
            text="Test text",
        )
        test_session.add(cue)

        with pytest.raises(IntegrityError):
            test_session.flush()

    def test_transcript_cue_end_time_not_null_constraint(self, test_session):
        """Given: TranscriptCue without end_time
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
            segment_id="segment_001",
            start_time=0.0,
            end_time=30.0,
        )
        test_session.add(segment)
        test_session.flush()

        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=0.0,
            # end_time is missing
            text="Test text",
        )
        test_session.add(cue)

        with pytest.raises(IntegrityError):
            test_session.flush()

    def test_transcript_cue_speaker_not_null_constraint(self, test_session):
        """Given: TranscriptCue without speaker
        When: Attempting to save
        Then: Uses default value 'Unknown'
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

        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=0.0,
            end_time=3.0,
            text="Test text",
            # speaker is missing
        )
        test_session.add(cue)
        test_session.flush()

        # Should have default value
        assert cue.speaker == "Unknown"

    def test_transcript_cue_text_not_null_constraint(self, test_session):
        """Given: TranscriptCue without text
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
            segment_id="segment_001",
            start_time=0.0,
            end_time=30.0,
        )
        test_session.add(segment)
        test_session.flush()

        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=0.0,
            end_time=3.0,
            # text is missing
        )
        test_session.add(cue)

        with pytest.raises(IntegrityError):
            test_session.flush()


class TestTranscriptCueProperties:
    """Test TranscriptCue properties."""

    def test_transcript_cue_duration_property(self, test_session):
        """Given: TranscriptCue with start_time and end_time
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
            segment_id="segment_001",
            start_time=0.0,
            end_time=30.0,
        )
        test_session.add(segment)
        test_session.flush()

        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=2.5,
            end_time=6.0,
            text="Test text",
        )
        test_session.add(cue)
        test_session.flush()

        assert cue.duration == 3.5


class TestTranscriptCueRelationships:
    """Test TranscriptCue relationships."""

    def test_transcript_cue_belongs_to_segment(self, test_session):
        """Given: TranscriptCue with segment_id
        When: Accessing segment relationship
        Then: Returns correct AudioSegment object
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

        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=0.0,
            end_time=3.0,
            text="Test text",
        )
        test_session.add(cue)
        test_session.flush()

        # Refresh to load relationship
        test_session.refresh(cue)
        test_session.refresh(segment)

        assert cue.segment.id == segment.id
        assert cue.segment.segment_id == "segment_001"

    def test_transcript_cue_episode_id_property(self, test_session):
        """Given: TranscriptCue with segment
        When: Accessing episode_id property
        Then: Returns correct episode_id from segment
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

        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=0.0,
            end_time=3.0,
            text="Test text",
        )
        test_session.add(cue)
        test_session.flush()

        # Refresh to load relationship
        test_session.refresh(cue)

        assert cue.episode_id == episode.id

    def test_transcript_cue_episode_property(self, test_session):
        """Given: TranscriptCue with segment
        When: Accessing episode property
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
            segment_id="segment_001",
            start_time=0.0,
            end_time=30.0,
        )
        test_session.add(segment)
        test_session.flush()

        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=0.0,
            end_time=3.0,
            text="Test text",
        )
        test_session.add(cue)
        test_session.flush()

        # Refresh to load relationship
        test_session.refresh(cue)

        assert cue.episode.id == episode.id
        assert cue.episode.title == "Test Episode"


class TestTranscriptCueRepr:
    """Test TranscriptCue __repr__ method."""

    def test_transcript_cue_repr_contains_id_and_text_preview(self, test_session):
        """Given: TranscriptCue object
        When: Calling repr()
        Then: Returns string with id and text preview
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

        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=0.0,
            end_time=3.0,
            text="This is a longer text for preview.",
        )
        test_session.add(cue)
        test_session.flush()

        result = repr(cue)

        assert "TranscriptCue" in result
        assert f"id={cue.id}" in result
        assert "This is a" in result  # Text preview
