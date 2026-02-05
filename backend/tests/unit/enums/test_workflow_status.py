"""
Unit tests for WorkflowStatus enumeration.

Test Naming Convention (BDD):
- test_<behavior>_<expected_result>
"""
import pytest

from app.enums.workflow_status import WorkflowStatus


class TestWorkflowStatus:
    """Test WorkflowStatus enumeration."""

    def test_workflow_status_init_value_is_zero(self):
        """Given: WorkflowStatus enum
        When: Accessing INIT
        Then: Value equals 0
        """
        assert WorkflowStatus.INIT.value == 0

    def test_workflow_status_published_value_is_six(self):
        """Given: WorkflowStatus enum
        When: Accessing PUBLISHED
        Then: Value equals 6
        """
        assert WorkflowStatus.PUBLISHED.value == 6

    def test_workflow_status_get_next_status_from_init(self):
        """Given: INIT status
        When: Calling get_next_status()
        Then: Returns DOWNLOADED (value 1)
        """
        result = WorkflowStatus.INIT.get_next_status()
        assert result == WorkflowStatus.DOWNLOADED
        assert result.value == 1

    def test_workflow_status_get_next_status_from_downloaded(self):
        """Given: DOWNLOADED status
        When: Calling get_next_status()
        Then: Returns TRANSCRIBED (value 2)
        """
        result = WorkflowStatus.DOWNLOADED.get_next_status()
        assert result == WorkflowStatus.TRANSCRIBED
        assert result.value == 2

    def test_workflow_status_get_next_status_from_published_returns_self(self):
        """Given: PUBLISHED status (final state)
        When: Calling get_next_status()
        Then: Returns PUBLISHED (no further state)
        """
        result = WorkflowStatus.PUBLISHED.get_next_status()
        assert result == WorkflowStatus.PUBLISHED
        assert result.value == 6

    def test_workflow_status_label_returns_chinese_text(self):
        """Given: WorkflowStatus enum
        When: Accessing label property
        Then: Returns Chinese text
        """
        assert WorkflowStatus.INIT.label == "已初始化"
        assert WorkflowStatus.DOWNLOADED.label == "已下载"
        assert WorkflowStatus.TRANSCRIBED.label == "已转录"
        assert WorkflowStatus.SEGMENTED.label == "已分章"
        assert WorkflowStatus.TRANSLATED.label == "已翻译"
        assert WorkflowStatus.READY_FOR_REVIEW.label == "待审核"
        assert WorkflowStatus.PUBLISHED.label == "已发布"
