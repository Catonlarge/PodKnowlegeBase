"""
Unit tests for TranslationCorrection model.

Test Naming Convention (BDD):
- test_<behavior>_<expected_result>
"""
import pytest

from sqlalchemy.exc import IntegrityError

from app.models.translation_correction import TranslationCorrection
from app.models.transcript_cue import TranscriptCue
from app.models.audio_segment import AudioSegment
from app.models.episode import Episode


class TestTranslationCorrectionCreate:
    """Test TranslationCorrection creation."""

    def test_translation_correction_create_minimal_fields(self, test_session):
        """Given: Database session and cue
        When: Creating TranslationCorrection with minimal fields
        Then: TranslationCorrection is created with correct defaults
        """
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

        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=0.5,
            end_time=3.5,
            text="Hello world.",
        )
        test_session.add(cue)
        test_session.flush()

        correction = TranslationCorrection(
            cue_id=cue.id,
            language_code="zh",
            original_text="原始翻译",
            corrected_text="修正后翻译",
        )
        test_session.add(correction)
        test_session.flush()

        assert correction.id is not None
        assert correction.cue_id == cue.id
        assert correction.language_code == "zh"
        assert correction.original_text == "原始翻译"
        assert correction.corrected_text == "修正后翻译"
        assert correction.ai_model is None

    def test_translation_correction_create_full_fields(self, test_session):
        """Given: Database session and cue
        When: Creating TranslationCorrection with all fields
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
            text="This is a test.",
        )
        test_session.add(cue)
        test_session.flush()

        correction = TranslationCorrection(
            cue_id=cue.id,
            language_code="ja",
            original_text="Original text",
            corrected_text="Corrected text",
            ai_model="gpt-4",
        )
        test_session.add(correction)
        test_session.flush()

        assert correction.cue_id == cue.id
        assert correction.language_code == "ja"
        assert correction.original_text == "Original text"
        assert correction.corrected_text == "Corrected text"
        assert correction.ai_model == "gpt-4"


class TestTranslationCorrectionConstraints:
    """Test TranslationCorrection database constraints."""

    def test_translation_correction_cue_id_not_null_constraint(self, test_session):
        """Given: TranslationCorrection without cue_id
        When: Attempting to save
        Then: Raises IntegrityError
        """
        correction = TranslationCorrection(
            # cue_id is missing
            language_code="zh",
            original_text="Original",
            corrected_text="Corrected",
        )
        test_session.add(correction)

        with pytest.raises(IntegrityError):
            test_session.flush()

    def test_translation_correction_language_code_not_null_constraint(self, test_session):
        """Given: TranslationCorrection without language_code
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
            text="Test text",
        )
        test_session.add(cue)
        test_session.flush()

        correction = TranslationCorrection(
            cue_id=cue.id,
            # language_code is missing
            original_text="Original",
            corrected_text="Corrected",
        )
        test_session.add(correction)

        with pytest.raises(IntegrityError):
            test_session.flush()

    def test_translation_correction_original_text_not_null_constraint(self, test_session):
        """Given: TranslationCorrection without original_text
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
            text="Test text",
        )
        test_session.add(cue)
        test_session.flush()

        correction = TranslationCorrection(
            cue_id=cue.id,
            language_code="zh",
            # original_text is missing
            corrected_text="Corrected",
        )
        test_session.add(correction)

        with pytest.raises(IntegrityError):
            test_session.flush()

    def test_translation_correction_corrected_text_not_null_constraint(self, test_session):
        """Given: TranslationCorrection without corrected_text
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
            text="Test text",
        )
        test_session.add(cue)
        test_session.flush()

        correction = TranslationCorrection(
            cue_id=cue.id,
            language_code="zh",
            original_text="Original",
            # corrected_text is missing
        )
        test_session.add(correction)

        with pytest.raises(IntegrityError):
            test_session.flush()


class TestTranslationCorrectionRelationships:
    """Test TranslationCorrection relationships."""

    def test_translation_correction_belongs_to_cue(self, test_session):
        """Given: TranslationCorrection with cue_id
        When: Accessing cue relationship
        Then: Returns correct TranscriptCue object
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

        correction = TranslationCorrection(
            cue_id=cue.id,
            language_code="zh",
            original_text="Original",
            corrected_text="Corrected",
        )
        test_session.add(correction)
        test_session.flush()

        # Refresh to load relationship
        test_session.refresh(correction)
        test_session.refresh(cue)

        assert correction.cue.id == cue.id
        assert correction.cue.text == "Test text"


class TestTranslationCorrectionRepr:
    """Test TranslationCorrection __repr__ method."""

    def test_translation_correction_repr_contains_id_and_language(self, test_session):
        """Given: TranslationCorrection object
        When: Calling repr()
        Then: Returns string with id and language_code
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

        correction = TranslationCorrection(
            cue_id=cue.id,
            language_code="zh",
            original_text="Original",
            corrected_text="Corrected",
        )
        test_session.add(correction)
        test_session.flush()

        result = repr(correction)

        assert "TranslationCorrection" in result
        assert f"id={correction.id}" in result
        assert "zh" in result
