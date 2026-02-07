"""
SubtitleProofreadingService Unit Tests

Updated for StructuredLLM migration with Pydantic validation.
"""
import json
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch

import pytest
from sqlalchemy.orm import object_session

from app.database import get_session
from app.services.subtitle_proofreading_service import (
    SubtitleProofreadingService,
    CorrectionResult,
    CorrectionSummary
)
from app.models import Episode, TranscriptCue, TranscriptCorrection, AudioSegment


@pytest.fixture(scope="function")
def sample_episode_with_cues(test_session):
    """Create test Episode with TranscriptCues"""
    episode = Episode(
        title="Test Episode",
        file_hash="test_proofread_001",
        duration=300.0,
        workflow_status=2,  # TRANSCRIBED
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

    # Create some test cues
    cues = []
    test_texts = [
        "Helo world, this is a test.",
        "How are you doing today?",
        "I am fine thank you.",
        "This is a grat day.",
    ]
    for i, text in enumerate(test_texts):
        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=float(i * 5),
            end_time=float((i + 1) * 5),
            speaker="SPEAKER_1",
            text=text
        )
        test_session.add(cue)
        cues.append(cue)

    test_session.commit()
    for cue in cues:
        test_session.refresh(cue)

    return episode, cues


class TestSubtitleProofreadingServiceInit:
    """Test SubtitleProofreadingService initialization"""

    @patch("app.services.subtitle_proofreading_service.MOONSHOT_API_KEY", None)
    def test_init_with_db_only(self, test_session):
        """
        Given: Database session, no API key
        When: Creating service without provider
        Then: Service is created successfully with no StructuredLLM
        """
        service = SubtitleProofreadingService(
            test_session,
            provider="moonshot",
            api_key=None
        )
        assert service.db == test_session
        assert service.structured_llm is None

    @patch("app.services.subtitle_proofreading_service.MOONSHOT_API_KEY", "test_key")
    def test_init_with_provider(self, test_session):
        """
        Given: Database session and API key
        When: Creating service with provider
        Then: Service initializes StructuredLLM
        """
        with patch("app.services.subtitle_proofreading_service.StructuredLLM") as mock_llm_class:
            mock_llm = Mock()
            mock_llm_class.return_value = mock_llm

            service = SubtitleProofreadingService(
                test_session,
                provider="moonshot"
            )
            assert service.provider == "moonshot"
            assert service.structured_llm == mock_llm


class TestScanAndCorrect:
    """Test scan_and_correct method"""

    @patch("app.services.subtitle_proofreading_service.MOONSHOT_API_KEY", None)
    def test_scan_and_correct_episode_not_found(self, test_session):
        """
        Given: Non-existent episode_id
        When: Calling scan_and_correct()
        Then: Raises ValueError
        """
        service = SubtitleProofreadingService(test_session, provider="moonshot", api_key=None)
        with pytest.raises(ValueError, match="Episode not found"):
            service.scan_and_correct(episode_id=999)

    @patch("app.services.subtitle_proofreading_service.MOONSHOT_API_KEY", None)
    def test_scan_and_correct_no_cues(self, test_session):
        """
        Given: Episode with no cues
        When: Calling scan_and_correct()
        Then: Raises ValueError
        """
        episode = Episode(
            title="Empty Episode",
            file_hash="empty_001",
            duration=60.0
        )
        test_session.add(episode)
        test_session.commit()

        service = SubtitleProofreadingService(test_session, provider="moonshot", api_key=None)
        with pytest.raises(ValueError, match="No cues found"):
            service.scan_and_correct(episode_id=episode.id)

    @patch("app.services.subtitle_proofreading_service.MOONSHOT_API_KEY", None)
    def test_scan_and_correct_without_llm(self, sample_episode_with_cues):
        """
        Given: Episode with cues, no LLM service
        When: Calling scan_and_correct()
        Then: Returns result with zero corrections
        """
        episode, cues = sample_episode_with_cues
        test_session = object_session(episode)
        service = SubtitleProofreadingService(test_session, provider="moonshot", api_key=None)
        result = service.scan_and_correct(episode.id, apply=False)

        assert result.total_cues == len(cues)
        assert result.corrected_count == 0
        assert len(result.corrections) == 0

    @patch("app.services.subtitle_proofreading_service.MOONSHOT_API_KEY", None)
    def test_scan_and_correct_checkpoint_resume(self, sample_episode_with_cues):
        """
        Given: Episode with some cues already corrected
        When: Calling scan_and_correct()
        Then: Skips already corrected cues
        """
        episode, cues = sample_episode_with_cues
        # Mark first cue as corrected
        cues[0].is_corrected = True
        cues[0].corrected_text = "Already corrected text"
        test_session = object_session(cues[0])
        test_session.commit()

        service = SubtitleProofreadingService(test_session, provider="moonshot", api_key=None)
        result = service.scan_and_correct(episode.id, apply=False)

        assert result.total_cues == len(cues)
        assert result.skipped_count == 1

    @patch('app.services.subtitle_proofreading_service.SubtitleProofreadingService._scan_batch')
    @patch("app.services.subtitle_proofreading_service.MOONSHOT_API_KEY", None)
    def test_scan_and_correct_with_mock_llm(self, mock_scan_batch, sample_episode_with_cues):
        """
        Given: Episode with cues and mock LLM returning corrections
        When: Calling scan_and_correct(apply=True)
        Then: Corrections are applied to database
        """
        episode, cues = sample_episode_with_cues
        test_session = object_session(cues[0])

        mock_corrections = [
            {
                "cue_id": cues[0].id,
                "original_text": "Helo",
                "corrected_text": "Hello",
                "reason": "拼写错误",
                "confidence": 0.95
            },
            {
                "cue_id": cues[3].id,
                "original_text": "grat",
                "corrected_text": "great",
                "reason": "拼写错误",
                "confidence": 0.90
            },
        ]
        mock_scan_batch.return_value = mock_corrections

        service = SubtitleProofreadingService(test_session, provider="moonshot", api_key=None)
        result = service.scan_and_correct(episode.id, apply=True)

        assert result.corrected_count == 2

        # Verify corrections were applied
        test_session.refresh(cues[0])
        test_session.refresh(cues[3])
        assert cues[0].is_corrected is True
        assert cues[0].corrected_text == "Hello"
        assert cues[3].is_corrected is True
        assert cues[3].corrected_text == "great"

        # Verify TranscriptCorrection records were created
        corrections = test_session.query(TranscriptCorrection).filter(
            TranscriptCorrection.cue_id == cues[0].id
        ).all()
        assert len(corrections) == 1
        assert corrections[0].applied is True


class TestScanBatch:
    """Test _scan_batch method"""

    @patch("app.services.subtitle_proofreading_service.MOONSHOT_API_KEY", None)
    def test_scan_batch_empty_list(self, test_session):
        """
        Given: Empty cue list
        When: Calling _scan_batch()
        Then: Returns empty list
        """
        service = SubtitleProofreadingService(test_session, provider="moonshot", api_key=None)
        result = service._scan_batch([])
        assert result == []

    @patch('app.services.subtitle_proofreading_service.StructuredLLM')
    @patch("app.services.subtitle_proofreading_service.MOONSHOT_API_KEY", "test_key")
    def test_scan_batch_with_llm_success(self, mock_structured_llm_class, sample_episode_with_cues):
        """
        Given: List of cues and mock StructuredLLM response
        When: LLM returns valid ProofreadingResponse
        Then: Returns list of dict correction objects
        """
        episode, cues = sample_episode_with_cues
        test_session = object_session(cues[0])

        # Create mock StructuredLLM and response
        from app.services.ai.schemas.proofreading_schema import ProofreadingResponse, CorrectionSuggestion

        mock_response = ProofreadingResponse(corrections=[
            CorrectionSuggestion(
                cue_id=cues[0].id,
                original_text="Helo",
                corrected_text="Hello",
                reason="拼写错误",
                confidence=0.95
            )
        ])

        mock_wrapper = Mock()
        mock_wrapper.invoke.return_value = mock_response

        mock_llm = Mock()
        mock_llm.with_structured_output.return_value = mock_wrapper
        mock_structured_llm_class.return_value = mock_llm

        service = SubtitleProofreadingService(test_session, provider="moonshot")

        result = service._scan_batch(cues[:2])

        assert len(result) == 1
        assert result[0]["cue_id"] == cues[0].id
        assert result[0]["original_text"] == "Helo"
        assert result[0]["corrected_text"] == "Hello"
        assert result[0]["reason"] == "拼写错误"
        assert result[0]["confidence"] == 0.95


class TestApplyCorrections:
    """Test apply_corrections method"""

    @patch("app.services.subtitle_proofreading_service.MOONSHOT_API_KEY", None)
    def test_apply_corrections_updates_database(self, sample_episode_with_cues):
        """
        Given: List of correction suggestions
        When: Calling apply_corrections()
        Then: TranscriptCue and TranscriptCorrection are updated
        """
        episode, cues = sample_episode_with_cues
        test_session = object_session(cues[0])

        corrections = [
            {
                "cue_id": cues[0].id,
                "original_text": "Helo world",
                "corrected_text": "Hello world",
                "reason": "拼写错误",
                "confidence": 0.95
            }
        ]

        service = SubtitleProofreadingService(test_session, provider="moonshot", api_key=None)
        count = service.apply_corrections(corrections)

        assert count == 1
        test_session.refresh(cues[0])
        assert cues[0].is_corrected is True
        assert cues[0].corrected_text == "Hello world"

        # Check TranscriptCorrection record
        corr_records = test_session.query(TranscriptCorrection).filter(
            TranscriptCorrection.cue_id == cues[0].id
        ).all()
        assert len(corr_records) == 1
        assert corr_records[0].applied is True

    @patch("app.services.subtitle_proofreading_service.MOONSHOT_API_KEY", None)
    def test_apply_corrections_skips_missing_cue(self, sample_episode_with_cues):
        """
        Given: Corrections with non-existent cue_id
        When: Calling apply_corrections()
        Then: Skips missing cue, processes others
        """
        episode, cues = sample_episode_with_cues
        test_session = object_session(cues[0])

        corrections = [
            {
                "cue_id": 9999,  # Non-existent
                "original_text": "test",
                "corrected_text": "corrected",
                "reason": "test",
                "confidence": 0.9
            }
        ]

        service = SubtitleProofreadingService(test_session, provider="moonshot", api_key=None)
        count = service.apply_corrections(corrections)
        assert count == 0


class TestGetCorrectionSummary:
    """Test get_correction_summary method"""

    @patch("app.services.subtitle_proofreading_service.MOONSHOT_API_KEY", None)
    def test_get_correction_summary(self, sample_episode_with_cues):
        """
        Given: Episode with corrections
        When: Calling get_correction_summary()
        Then: Returns correct summary statistics
        """
        episode, cues = sample_episode_with_cues
        test_session = object_session(cues[0])

        # Mark some cues as corrected
        cues[0].is_corrected = True
        cues[1].is_corrected = True
        test_session.commit()

        service = SubtitleProofreadingService(test_session, provider="moonshot", api_key=None)
        summary = service.get_correction_summary(episode.id)

        assert summary.episode_id == episode.id
        assert summary.total_cues == len(cues)
        assert summary.corrected_cues == 2
        assert summary.correction_rate == 2.0 / len(cues)

    @patch("app.services.subtitle_proofreading_service.MOONSHOT_API_KEY", None)
    def test_get_correction_summary_episode_not_found(self, test_session):
        """
        Given: Non-existent episode_id
        When: Calling get_correction_summary()
        Then: Raises ValueError
        """
        service = SubtitleProofreadingService(test_session, provider="moonshot", api_key=None)
        with pytest.raises(ValueError, match="Episode not found"):
            service.get_correction_summary(999)
