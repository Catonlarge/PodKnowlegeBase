"""
Unit tests for TranslationStatus enumeration.

Test Naming Convention (BDD):
- test_<behavior>_<expected_result>
"""
import pytest

from app.enums.translation_status import TranslationStatus


class TestTranslationStatus:
    """Test TranslationStatus enumeration."""

    def test_translation_status_pending_value(self):
        """Given: TranslationStatus enum
        When: Accessing PENDING
        Then: Value equals "pending"
        """
        assert TranslationStatus.PENDING.value == "pending"

    def test_translation_status_processing_value(self):
        """Given: TranslationStatus enum
        When: Accessing PROCESSING
        Then: Value equals "processing"
        """
        assert TranslationStatus.PROCESSING.value == "processing"

    def test_translation_status_completed_value(self):
        """Given: TranslationStatus enum
        When: Accessing COMPLETED
        Then: Value equals "completed"
        """
        assert TranslationStatus.COMPLETED.value == "completed"

    def test_translation_status_failed_value(self):
        """Given: TranslationStatus enum
        When: Accessing FAILED
        Then: Value equals "failed"
        """
        assert TranslationStatus.FAILED.value == "failed"

    def test_translation_status_label_returns_chinese_text(self):
        """Given: TranslationStatus enum
        When: Accessing label property
        Then: Returns Chinese text
        """
        assert TranslationStatus.PENDING.label == "等待翻译"
        assert TranslationStatus.PROCESSING.label == "翻译中"
        assert TranslationStatus.COMPLETED.label == "翻译完成"
        assert TranslationStatus.FAILED.label == "翻译失败"
