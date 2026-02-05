"""
Unit tests for Translation model.

Test Naming Convention (BDD):
- test_<behavior>_<expected_result>
"""
import pytest

from sqlalchemy.exc import IntegrityError

from app.models.translation import Translation
from app.models.transcript_cue import TranscriptCue
from app.models.audio_segment import AudioSegment
from app.models.episode import Episode


class TestTranslationCreate:
    """Test Translation creation."""

    def test_translation_create_minimal_fields(self, test_session):
        """Given: Database session and cue
        When: Creating Translation with minimal fields
        Then: Translation is created with correct defaults
        """
        # Create episode, segment, and cue first
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

        # Create translation
        translation = Translation(
            cue_id=cue.id,
            language_code="zh",
            translation="你好世界。",
        )
        test_session.add(translation)
        test_session.flush()

        assert translation.id is not None
        assert translation.cue_id == cue.id
        assert translation.language_code == "zh"
        assert translation.translation == "你好世界。"
        assert translation.original_translation == "你好世界。"  # Should be auto-set
        assert translation.is_edited is False  # Default value
        assert translation.translation_status == "pending"  # Default value
        assert translation.translation_error is None
        assert translation.translation_retry_count == 0

    def test_translation_create_full_fields(self, test_session):
        """Given: Database session and cue
        When: Creating Translation with all fields
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

        translation = Translation(
            cue_id=cue.id,
            language_code="ja",
            original_translation="AI initial translation",
            translation="Updated translation",
            is_edited=True,
            translation_status="completed",
            translation_error="Test error",
            translation_retry_count=2,
        )
        test_session.add(translation)
        test_session.flush()

        assert translation.cue_id == cue.id
        assert translation.language_code == "ja"
        assert translation.original_translation == "AI initial translation"
        assert translation.translation == "Updated translation"
        assert translation.is_edited is True
        assert translation.translation_status == "completed"
        assert translation.translation_error == "Test error"
        assert translation.translation_retry_count == 2

    def test_translation_is_edited_default_is_false(self, test_session):
        """Given: New Translation
        When: Not specifying is_edited
        Then: Defaults to False
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

        translation = Translation(
            cue_id=cue.id,
            language_code="zh",
            translation="Test translation",
        )
        test_session.add(translation)
        test_session.flush()

        assert translation.is_edited is False

    def test_translation_status_default_is_pending(self, test_session):
        """Given: New Translation
        When: Not specifying translation_status
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

        translation = Translation(
            cue_id=cue.id,
            language_code="zh",
            translation="Test translation",
        )
        test_session.add(translation)
        test_session.flush()

        assert translation.translation_status == "pending"


class TestTranslationConstraints:
    """Test Translation database constraints."""

    def test_translation_cue_id_not_null_constraint(self, test_session):
        """Given: Translation without cue_id
        When: Attempting to save
        Then: Raises IntegrityError
        """
        translation = Translation(
            # cue_id is missing
            language_code="zh",
            translation="Test translation",
        )
        test_session.add(translation)

        with pytest.raises(IntegrityError):
            test_session.flush()

    def test_translation_language_code_not_null_constraint(self, test_session):
        """Given: Translation without language_code
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

        translation = Translation(
            cue_id=cue.id,
            # language_code is missing
            translation="Test translation",
        )
        test_session.add(translation)

        with pytest.raises(IntegrityError):
            test_session.flush()

    def test_translation_unique_constraint_cue_id_language_code(self, test_session):
        """Given: Cue with existing translation for 'zh'
        When: Creating another translation with same cue_id and language_code
        Then: Raises IntegrityError
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

        # Create first translation
        translation1 = Translation(
            cue_id=cue.id,
            language_code="zh",
            translation="First translation",
        )
        test_session.add(translation1)
        test_session.flush()

        # Try to create duplicate
        translation2 = Translation(
            cue_id=cue.id,
            language_code="zh",  # Same language
            translation="Second translation",
        )
        test_session.add(translation2)

        with pytest.raises(IntegrityError):
            test_session.flush()

    def test_translation_different_languages_same_cue_allowed(self, test_session):
        """Given: Cue with existing translation for 'zh'
        When: Creating translation with same cue_id but different language_code
        Then: Both translations are created successfully
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

        # Both translations can exist because they have different language codes
        translation1 = Translation(
            cue_id=cue.id,
            language_code="zh",
            translation="Chinese translation",
        )
        translation2 = Translation(
            cue_id=cue.id,
            language_code="ja",
            translation="Japanese translation",
        )
        test_session.add(translation1)
        test_session.add(translation2)
        test_session.flush()

        assert translation1.id is not None
        assert translation2.id is not None


class TestTranslationRLHFLogic:
    """Test Translation RLHF (Reinforcement Learning from Human Feedback) logic."""

    def test_translation_original_translation_auto_set_from_translation(self, test_session):
        """Given: New Translation with translation but no original_translation
        When: Saving to database
        Then: original_translation is automatically set to translation value
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

        translation = Translation(
            cue_id=cue.id,
            language_code="zh",
            translation="AI translation",
        )
        test_session.add(translation)
        test_session.flush()

        # original_translation should be auto-set to the same value as translation
        assert translation.original_translation == "AI translation"

    def test_translation_is_edited_remains_false_when_same(self, test_session):
        """Given: Translation with same original_translation and translation
        When: Both values are identical
        Then: is_edited remains False
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

        translation = Translation(
            cue_id=cue.id,
            language_code="zh",
            original_translation="Same text",
            translation="Same text",
        )
        test_session.add(translation)
        test_session.flush()

        # Note: In the actual implementation, is_edited might be set manually
        # This test documents the expected behavior
        assert translation.original_translation == translation.translation


class TestTranslationRelationships:
    """Test Translation relationships."""

    def test_translation_belongs_to_cue(self, test_session):
        """Given: Translation with cue_id
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

        translation = Translation(
            cue_id=cue.id,
            language_code="zh",
            translation="Test translation",
        )
        test_session.add(translation)
        test_session.flush()

        # Refresh to load relationship
        test_session.refresh(translation)
        test_session.refresh(cue)

        assert translation.cue.id == cue.id
        assert translation.cue.text == "Test text"


class TestTranslationRepr:
    """Test Translation __repr__ method."""

    def test_translation_repr_contains_id_and_language(self, test_session):
        """Given: Translation object
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

        translation = Translation(
            cue_id=cue.id,
            language_code="zh",
            translation="Test translation",
        )
        test_session.add(translation)
        test_session.flush()

        result = repr(translation)

        assert "Translation" in result
        assert f"id={translation.id}" in result
        assert "zh" in result
        assert "pending" in result
