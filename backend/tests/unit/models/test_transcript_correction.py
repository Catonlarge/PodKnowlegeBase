"""
TranscriptCorrection Model Unit Tests
"""
import pytest
from sqlalchemy import exc

from app.models.transcript_correction import TranscriptCorrection
from app.models.transcript_cue import TranscriptCue
from app.models.audio_segment import AudioSegment
from app.models.episode import Episode


@pytest.fixture(scope="function")
def sample_cue(test_session):
    """Create test TranscriptCue"""
    episode = Episode(
        title="Test Episode",
        file_hash="test_hash_001",
        duration=300.0,
        source_url="https://test.com/audio.mp3"
    )
    test_session.add(episode)
    test_session.flush()

    segment = AudioSegment(
        episode_id=episode.id,
        segment_index=0,
        segment_id="seg_001",
        start_time=0.0,
        end_time=30.0
    )
    test_session.add(segment)
    test_session.flush()

    cue = TranscriptCue(
        segment_id=segment.id,
        start_time=0.0,
        end_time=5.0,
        speaker="SPEAKER_1",
        text="Helo world, this is a test."
    )
    test_session.add(cue)
    test_session.commit()
    test_session.refresh(cue)
    return cue


class TestTranscriptCorrectionCreate:
    """Test creating TranscriptCorrection"""

    def test_create_transcript_correction_minimal(self, test_session, sample_cue):
        """
        Given: Existing TranscriptCue
        When: Creating TranscriptCorrection with required fields only
        Then: Correction record is created with correct defaults
        """
        correction = TranscriptCorrection(
            cue_id=sample_cue.id,
            original_text="Helo world",
            corrected_text="Hello world"
        )
        test_session.add(correction)
        test_session.commit()
        test_session.refresh(correction)

        assert correction.id is not None
        assert correction.cue_id == sample_cue.id
        assert correction.original_text == "Helo world"
        assert correction.corrected_text == "Hello world"
        assert correction.reason is None
        assert correction.confidence is None
        assert correction.ai_model is None
        assert correction.applied is False

    def test_create_transcript_correction_full(self, test_session, sample_cue):
        """
        Given: Existing TranscriptCue
        When: Creating TranscriptCorrection with all fields
        Then: All field values are correctly set
        """
        correction = TranscriptCorrection(
            cue_id=sample_cue.id,
            original_text="Helo world",
            corrected_text="Hello world",
            reason="拼写错误：Helo → Hello",
            confidence=0.95,
            ai_model="moonshot-v1-8k",
            applied=True
        )
        test_session.add(correction)
        test_session.commit()
        test_session.refresh(correction)

        assert correction.reason == "拼写错误：Helo → Hello"
        assert correction.confidence == 0.95
        assert correction.ai_model == "moonshot-v1-8k"
        assert correction.applied is True

    def test_create_multiple_corrections_same_cue(self, test_session, sample_cue):
        """
        Given: Existing TranscriptCue
        When: Creating multiple correction records for same cue (history)
        Then: All records are created (no unique constraint)
        """
        correction1 = TranscriptCorrection(
            cue_id=sample_cue.id,
            original_text="Helo",
            corrected_text="Hello"
        )
        correction2 = TranscriptCorrection(
            cue_id=sample_cue.id,
            original_text="Helo",
            corrected_text="Hello There"
        )
        test_session.add(correction1)
        test_session.add(correction2)
        test_session.commit()

        corrections = test_session.query(TranscriptCorrection).filter(
            TranscriptCorrection.cue_id == sample_cue.id
        ).all()

        assert len(corrections) == 2


class TestTranscriptCorrectionConstraints:
    """Test database constraints"""

    def test_cue_id_not_null(self, test_session):
        """
        Given: Preparing to create TranscriptCorrection
        When: cue_id is None
        Then: Raises IntegrityError
        """
        with pytest.raises(exc.IntegrityError):
            correction = TranscriptCorrection(
                cue_id=None,
                original_text="test",
                corrected_text="corrected"
            )
            test_session.add(correction)
            test_session.commit()

    def test_original_text_not_null(self, test_session, sample_cue):
        """
        Given: Preparing to create TranscriptCorrection
        When: original_text is None
        Then: Raises IntegrityError
        """
        with pytest.raises(exc.IntegrityError):
            correction = TranscriptCorrection(
                cue_id=sample_cue.id,
                original_text=None,
                corrected_text="corrected"
            )
            test_session.add(correction)
            test_session.commit()

    def test_corrected_text_not_null(self, test_session, sample_cue):
        """
        Given: Preparing to create TranscriptCorrection
        When: corrected_text is None
        Then: Raises IntegrityError
        """
        with pytest.raises(exc.IntegrityError):
            correction = TranscriptCorrection(
                cue_id=sample_cue.id,
                original_text="original",
                corrected_text=None
            )
            test_session.add(correction)
            test_session.commit()


class TestTranscriptCorrectionRelationships:
    """Test relationships"""

    def test_relationship_to_cue(self, test_session, sample_cue):
        """
        Given: Existing TranscriptCorrection
        When: Accessing cue relationship
        Then: Returns associated TranscriptCue
        """
        correction = TranscriptCorrection(
            cue_id=sample_cue.id,
            original_text="Helo",
            corrected_text="Hello"
        )
        test_session.add(correction)
        test_session.commit()
        test_session.refresh(correction)

        assert correction.cue.id == sample_cue.id
        assert correction.cue.text == sample_cue.text


class TestTranscriptCorrectionCascadeDelete:
    """Test cascade delete behavior"""

    def test_cascade_delete_when_cue_deleted(self, test_session, sample_cue):
        """
        Given: Associated TranscriptCorrection
        When: Deleting TranscriptCue through segment
        Then: TranscriptCorrection is cascade deleted
        """
        correction = TranscriptCorrection(
            cue_id=sample_cue.id,
            original_text="Helo",
            corrected_text="Hello"
        )
        test_session.add(correction)
        test_session.commit()
        correction_id = correction.id

        # Delete through segment
        test_session.delete(sample_cue.segment)
        test_session.commit()

        deleted_correction = test_session.query(TranscriptCorrection).get(correction_id)
        assert deleted_correction is None


class TestTranscriptCorrectionConfidence:
    """Test confidence field"""

    def test_confidence_range_valid(self, test_session, sample_cue):
        """
        Given: Creating TranscriptCorrection
        When: Setting confidence within 0-1 range
        Then: Values are correctly saved
        """
        correction_low = TranscriptCorrection(
            cue_id=sample_cue.id,
            original_text="test",
            corrected_text="corrected",
            confidence=0.0
        )
        correction_high = TranscriptCorrection(
            cue_id=sample_cue.id,
            original_text="test2",
            corrected_text="corrected2",
            confidence=1.0
        )
        test_session.add(correction_low)
        test_session.add(correction_high)
        test_session.commit()

        assert correction_low.confidence == 0.0
        assert correction_high.confidence == 1.0

    def test_confidence_nullable(self, test_session, sample_cue):
        """
        Given: Creating TranscriptCorrection
        When: Not setting confidence
        Then: confidence is None (nullable field)
        """
        correction = TranscriptCorrection(
            cue_id=sample_cue.id,
            original_text="test",
            corrected_text="corrected"
        )
        test_session.add(correction)
        test_session.commit()
        test_session.refresh(correction)

        assert correction.confidence is None


class TestTranscriptCorrectionRepr:
    """Test __repr__ method"""

    def test_repr_output(self, test_session, sample_cue):
        """
        Given: TranscriptCorrection object
        When: Calling repr()
        Then: Returns correct string representation
        """
        correction = TranscriptCorrection(
            cue_id=sample_cue.id,
            original_text="Helo",
            corrected_text="Hello"
        )
        test_session.add(correction)
        test_session.commit()
        test_session.refresh(correction)

        result = repr(correction)
        assert "TranscriptCorrection" in result
        assert str(correction.id) in result
