"""
Unit tests for TranscriptionService.

These tests use database sessions and mock WhisperService.
"""
import os
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch

import pytest

from app.models import Episode, AudioSegment, TranscriptCue
from app.services.transcription_service import TranscriptionService
from app.enums.workflow_status import WorkflowStatus
from app.enums.transcription_status import TranscriptionStatus


class TestTranscriptionServiceCreateVirtualSegments:
    """Test virtual segment creation."""

    def test_create_virtual_segments_creates_correct_count(self, test_session):
        """Given: Episode with duration=600s and SEGMENT_DURATION=180s
        When: Calling create_virtual_segments
        Then: Creates 4 segments
        """
        # Arrange
        episode = Episode(
            title="Test Episode",
            file_hash="abc123",
            duration=600.0,
            audio_path="tests/fixtures/test_audio.mp3",
        )
        test_session.add(episode)
        test_session.flush()

        mock_whisper = Mock()

        with patch('app.services.transcription_service.SEGMENT_DURATION', 180):
            service = TranscriptionService(test_session, mock_whisper)

            # Act
            segments = service.create_virtual_segments(episode)

            # Assert
            assert len(segments) == 4
            assert segments[0].start_time == 0.0
            assert segments[0].end_time == 180.0
            assert segments[3].start_time == 540.0
            assert segments[3].end_time == 600.0

    def test_create_virtual_segments_skips_if_existing(self, test_session):
        """Given: Episode with existing segments
        When: Calling create_virtual_segments
        Then: Returns existing segments without creating new ones
        """
        # Arrange
        episode = Episode(
            title="Test Episode",
            file_hash="abc123",
            duration=180.0,
        )
        test_session.add(episode)
        test_session.flush()

        # Create existing segment
        existing_segment = AudioSegment(
            episode_id=episode.id,
            segment_index=0,
            segment_id="segment_000",
            start_time=0.0,
            end_time=180.0,
        )
        test_session.add(existing_segment)
        test_session.flush()

        mock_whisper = Mock()
        service = TranscriptionService(test_session, mock_whisper)

        # Act
        segments = service.create_virtual_segments(episode)

        # Assert
        assert len(segments) == 1
        assert segments[0].id == existing_segment.id


class TestTranscriptionServiceTranscribeSegment:
    """Test single segment transcription."""

    def test_transcribe_virtual_segment_saves_cues(self, test_session):
        """Given: AudioSegment and mock WhisperService
        When: Calling transcribe_virtual_segment
        Then: Saves TranscriptCue to database and updates segment status
        """
        # Arrange
        episode = Episode(
            title="Test Episode",
            file_hash="abc123",
            duration=180.0,
            audio_path="tests/fixtures/test_audio.mp3",
        )
        test_session.add(episode)
        test_session.flush()

        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=0,
            segment_id="segment_000",
            start_time=0.0,
            end_time=30.0,
        )
        test_session.add(segment)
        test_session.flush()

        # Mock WhisperService
        mock_cues = [
            {"start": 0.0, "end": 3.0, "speaker": "SPEAKER_00", "text": "Hello world"},
            {"start": 3.0, "end": 6.0, "speaker": "SPEAKER_00", "text": "Test transcription"},
        ]

        mock_whisper = Mock()
        mock_whisper.transcribe_segment.return_value = mock_cues
        mock_whisper.extract_segment_to_temp.return_value = "tests/fixtures/temp.wav"

        with patch('os.path.exists', return_value=True):
            service = TranscriptionService(test_session, mock_whisper)

            # Act
            cues_count = service.transcribe_virtual_segment(segment)

            # Assert
            assert cues_count == 2
            assert segment.status == TranscriptionStatus.COMPLETED.value

            # Verify TranscriptCue was saved
            saved_cues = test_session.query(TranscriptCue).filter(
                TranscriptCue.segment_id == segment.id
            ).all()
            assert len(saved_cues) == 2
            assert saved_cues[0].text == "Hello world"

    def test_transcribe_virtual_segment_skips_completed(self, test_session):
        """Given: Segment with status=completed
        When: Calling transcribe_virtual_segment
        Then: Skips transcription and returns existing cue count
        """
        # Arrange
        episode = Episode(
            title="Test Episode",
            file_hash="abc123",
            duration=180.0,
            audio_path="tests/fixtures/test_audio.mp3",
        )
        test_session.add(episode)
        test_session.flush()

        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=0,
            segment_id="segment_000",
            start_time=0.0,
            end_time=30.0,
            status=TranscriptionStatus.COMPLETED.value,
        )
        test_session.add(segment)
        test_session.flush()

        # Add existing cue
        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=0.0,
            end_time=3.0,
            speaker="SPEAKER_00",
            text="Existing cue",
        )
        test_session.add(cue)
        test_session.flush()

        mock_whisper = Mock()
        service = TranscriptionService(test_session, mock_whisper)

        # Act
        cues_count = service.transcribe_virtual_segment(segment)

        # Assert
        assert cues_count == 1
        mock_whisper.transcribe_segment.assert_not_called()


class TestTranscriptionServiceSaveCues:
    """Test cue saving to database."""

    def test_save_cues_to_db_calculates_absolute_time(self, test_session):
        """Given: Cues with relative time and segment with start_time=100
        When: Calling save_cues_to_db
        Then: Saves cues with absolute time (segment.start_time + cue.start)
        """
        # Arrange
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
            segment_id="segment_000",
            start_time=100.0,
            end_time=130.0,
        )
        test_session.add(segment)
        test_session.flush()

        cues = [
            {"start": 0.0, "end": 3.0, "speaker": "SPEAKER_00", "text": "First"},
            {"start": 5.0, "end": 8.0, "speaker": "SPEAKER_01", "text": "Second"},
        ]

        mock_whisper = Mock()
        service = TranscriptionService(test_session, mock_whisper)

        # Act
        count = service.save_cues_to_db(cues, segment)

        # Assert
        assert count == 2

        saved_cues = test_session.query(TranscriptCue).filter(
            TranscriptCue.segment_id == segment.id
        ).order_by(TranscriptCue.start_time).all()

        assert saved_cues[0].start_time == 100.0  # 100 + 0
        assert saved_cues[0].end_time == 103.0
        assert saved_cues[1].start_time == 105.0  # 100 + 5
        assert saved_cues[1].end_time == 108.0


class TestTranscriptionServiceSyncStatus:
    """Test episode status synchronization."""

    def test_sync_episode_status_updates_to_transcribed(self, test_session):
        """Given: Episode with all segments completed
        When: Calling sync_episode_transcription_status
        Then: Updates workflow_status to TRANSCRIBED
        """
        # Arrange
        episode = Episode(
            title="Test Episode",
            file_hash="abc123",
            duration=180.0,
            workflow_status=WorkflowStatus.DOWNLOADED.value,
        )
        test_session.add(episode)
        test_session.flush()

        # Create completed segments
        for i in range(3):
            segment = AudioSegment(
                episode_id=episode.id,
                segment_index=i,
                segment_id=f"segment_{i:03d}",
                start_time=i * 60.0,
                end_time=(i + 1) * 60.0,
                status=TranscriptionStatus.COMPLETED.value,
            )
            test_session.add(segment)
        test_session.flush()

        mock_whisper = Mock()
        service = TranscriptionService(test_session, mock_whisper)

        # Act
        service.sync_episode_transcription_status(episode.id)

        # Assert
        test_session.refresh(episode)
        assert episode.workflow_status == WorkflowStatus.TRANSCRIBED.value

    def test_sync_episode_status_keeps_downloaded_when_partial(self, test_session):
        """Given: Episode with some completed and some pending segments
        When: Calling sync_episode_transcription_status
        Then: Does not update workflow_status (keeps DOWNLOADED)
        """
        # Arrange
        episode = Episode(
            title="Test Episode",
            file_hash="abc123",
            duration=360.0,
            workflow_status=WorkflowStatus.DOWNLOADED.value,
        )
        test_session.add(episode)
        test_session.flush()

        # Mix of completed and pending
        segment1 = AudioSegment(
            episode_id=episode.id,
            segment_index=0,
            segment_id="segment_000",
            start_time=0.0,
            end_time=180.0,
            status=TranscriptionStatus.COMPLETED.value,
        )
        segment2 = AudioSegment(
            episode_id=episode.id,
            segment_index=1,
            segment_id="segment_001",
            start_time=180.0,
            end_time=360.0,
            status=TranscriptionStatus.PENDING.value,
        )
        test_session.add_all([segment1, segment2])
        test_session.flush()

        mock_whisper = Mock()
        service = TranscriptionService(test_session, mock_whisper)

        # Act
        service.sync_episode_transcription_status(episode.id)

        # Assert
        test_session.refresh(episode)
        assert episode.workflow_status == WorkflowStatus.DOWNLOADED.value
