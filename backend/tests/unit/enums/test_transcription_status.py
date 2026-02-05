"""
Unit tests for TranscriptionStatus enumeration.

Test Naming Convention (BDD):
- test_<behavior>_<expected_result>
"""
import pytest

from app.enums.transcription_status import TranscriptionStatus


class TestTranscriptionStatus:
    """Test TranscriptionStatus enumeration."""

    def test_transcription_status_pending_value(self):
        """Given: TranscriptionStatus enum
        When: Accessing PENDING
        Then: Value equals "pending"
        """
        assert TranscriptionStatus.PENDING.value == "pending"

    def test_transcription_status_processing_value(self):
        """Given: TranscriptionStatus enum
        When: Accessing PROCESSING
        Then: Value equals "processing"
        """
        assert TranscriptionStatus.PROCESSING.value == "processing"

    def test_transcription_status_completed_value(self):
        """Given: TranscriptionStatus enum
        When: Accessing COMPLETED
        Then: Value equals "completed"
        """
        assert TranscriptionStatus.COMPLETED.value == "completed"

    def test_transcription_status_failed_value(self):
        """Given: TranscriptionStatus enum
        When: Accessing FAILED
        Then: Value equals "failed"
        """
        assert TranscriptionStatus.FAILED.value == "failed"

    def test_transcription_status_label_returns_chinese_text(self):
        """Given: TranscriptionStatus enum
        When: Accessing label property
        Then: Returns Chinese text
        """
        assert TranscriptionStatus.PENDING.label == "等待转录"
        assert TranscriptionStatus.PROCESSING.label == "转录中"
        assert TranscriptionStatus.COMPLETED.label == "转录完成"
        assert TranscriptionStatus.FAILED.label == "转录失败"
