"""
WorkflowStateMachine Unit Tests
"""
from unittest.mock import Mock
from dataclasses import dataclass
from typing import List, Optional, Callable

import pytest

from app.database import get_session
from app.enums.workflow_status import WorkflowStatus
from app.models import Episode
from app.workflows.state_machine import (
    WorkflowStateMachine,
    WorkflowInfo,
)

# Import step functions from runner where they are implemented
from app.workflows.runner import (
    download_episode,
    transcribe_episode,
    proofread_episode,
    segment_episode,
    translate_episode,
    generate_obsidian_doc,
)


@pytest.fixture(scope="function")
def state_machine(test_session):
    """Create WorkflowStateMachine instance"""
    return WorkflowStateMachine(test_session)


@pytest.fixture(scope="function")
def sample_episode(test_session):
    """Create test Episode"""
    episode = Episode(
        title="Test Episode",
        file_hash="test_workflow_001",
        source_url="https://www.youtube.com/watch?v=test001",
        duration=300.0,
        workflow_status=WorkflowStatus.INIT,
    )
    test_session.add(episode)
    test_session.commit()
    test_session.refresh(episode)
    return episode


# Define step functions mapping for testing
STEP_FUNCTIONS = {
    WorkflowStatus.INIT: download_episode,
    WorkflowStatus.DOWNLOADED: transcribe_episode,
    WorkflowStatus.TRANSCRIBED: proofread_episode,
    WorkflowStatus.PROOFREAD: segment_episode,
    WorkflowStatus.SEGMENTED: translate_episode,
    WorkflowStatus.TRANSLATED: generate_obsidian_doc,
}


class TestGetNextStep:
    """Test get_next_step method"""

    def test_get_next_step_from_init_returns_download(self, state_machine, sample_episode):
        """
        Given: Episode with workflow_status=INIT
        When: Calling get_next_step()
        Then: Returns download_episode function
        """
        sample_episode.workflow_status = WorkflowStatus.INIT
        next_step = state_machine.get_next_step(sample_episode)

        assert next_step is not None
        assert next_step.__name__ == "download_episode"

    def test_get_next_step_from_downloaded_returns_transcribe(self, state_machine, sample_episode):
        """
        Given: Episode with workflow_status=DOWNLOADED
        When: Calling get_next_step()
        Then: Returns transcribe_episode function
        """
        sample_episode.workflow_status = WorkflowStatus.DOWNLOADED
        next_step = state_machine.get_next_step(sample_episode)

        assert next_step is not None
        assert next_step.__name__ == "transcribe_episode"

    def test_get_next_step_from_transcribed_returns_proofread(self, state_machine, sample_episode):
        """
        Given: Episode with workflow_status=TRANSCRIBED
        When: Calling get_next_step()
        Then: Returns proofread_episode function
        """
        sample_episode.workflow_status = WorkflowStatus.TRANSCRIBED
        next_step = state_machine.get_next_step(sample_episode)

        assert next_step is not None
        assert next_step.__name__ == "proofread_episode"

    def test_get_next_step_from_proofread_returns_segment(self, state_machine, sample_episode):
        """
        Given: Episode with workflow_status=PROOFREAD
        When: Calling get_next_step()
        Then: Returns segment_episode function
        """
        sample_episode.workflow_status = WorkflowStatus.PROOFREAD
        next_step = state_machine.get_next_step(sample_episode)

        assert next_step is not None
        assert next_step.__name__ == "segment_episode"

    def test_get_next_step_from_segmented_returns_translate(self, state_machine, sample_episode):
        """
        Given: Episode with workflow_status=SEGMENTED
        When: Calling get_next_step()
        Then: Returns translate_episode function
        """
        sample_episode.workflow_status = WorkflowStatus.SEGMENTED
        next_step = state_machine.get_next_step(sample_episode)

        assert next_step is not None
        assert next_step.__name__ == "translate_episode"

    def test_get_next_step_from_translated_returns_generate_doc(self, state_machine, sample_episode):
        """
        Given: Episode with workflow_status=TRANSLATED
        When: Calling get_next_step()
        Then: Returns generate_obsidian_doc function
        """
        sample_episode.workflow_status = WorkflowStatus.TRANSLATED
        next_step = state_machine.get_next_step(sample_episode)

        assert next_step is not None
        assert next_step.__name__ == "generate_obsidian_doc"

    def test_get_next_step_from_ready_for_review_returns_none(self, state_machine, sample_episode):
        """
        Given: Episode with workflow_status=READY_FOR_REVIEW
        When: Calling get_next_step()
        Then: Returns None (main workflow complete)
        """
        sample_episode.workflow_status = WorkflowStatus.READY_FOR_REVIEW
        next_step = state_machine.get_next_step(sample_episode)

        assert next_step is None

    def test_get_next_step_from_published_returns_none(self, state_machine, sample_episode):
        """
        Given: Episode with workflow_status=PUBLISHED
        When: Calling get_next_step()
        Then: Returns None (workflow complete)
        """
        sample_episode.workflow_status = WorkflowStatus.PUBLISHED
        next_step = state_machine.get_next_step(sample_episode)

        assert next_step is None


class TestCanResume:
    """Test can_resume method"""

    def test_can_resume_from_init_returns_false(self, state_machine, sample_episode):
        """
        Given: Episode with workflow_status=INIT
        When: Calling can_resume()
        Then: Returns (False, "新任务")
        """
        sample_episode.workflow_status = WorkflowStatus.INIT
        can_resume, message = state_machine.can_resume(sample_episode)

        assert can_resume is False
        assert "新任务" in message

    def test_can_resume_from_downloaded_returns_true(self, state_machine, sample_episode):
        """
        Given: Episode with workflow_status=DOWNLOADED
        When: Calling can_resume()
        Then: Returns (True, "检测到历史任务")
        """
        sample_episode.workflow_status = WorkflowStatus.DOWNLOADED
        can_resume, message = state_machine.can_resume(sample_episode)

        assert can_resume is True
        assert "检测到历史任务" in message
        assert "已下载" in message

    def test_can_resume_from_transcribed_returns_true(self, state_machine, sample_episode):
        """
        Given: Episode with workflow_status=TRANSCRIBED
        When: Calling can_resume()
        Then: Returns (True, "检测到历史任务: 已转录")
        """
        sample_episode.workflow_status = WorkflowStatus.TRANSCRIBED
        can_resume, message = state_machine.can_resume(sample_episode)

        assert can_resume is True
        assert "检测到历史任务" in message
        assert "已转录" in message

    def test_can_resume_from_published_returns_false(self, state_machine, sample_episode):
        """
        Given: Episode with workflow_status=PUBLISHED
        When: Calling can_resume()
        Then: Returns (False, "任务已完成")
        """
        sample_episode.workflow_status = WorkflowStatus.PUBLISHED
        can_resume, message = state_machine.can_resume(sample_episode)

        assert can_resume is False
        assert "已完成" in message


class TestGetWorkflowInfo:
    """Test get_workflow_info method"""

    def test_get_workflow_info_from_init(self, state_machine, sample_episode):
        """
        Given: Episode with workflow_status=INIT
        When: Calling get_workflow_info()
        Then: Returns correct WorkflowInfo with no completed steps
        """
        sample_episode.workflow_status = WorkflowStatus.INIT
        info = state_machine.get_workflow_info(sample_episode)

        assert info.episode_id == sample_episode.id
        assert info.current_status == WorkflowStatus.INIT
        assert len(info.completed_steps) == 0
        assert len(info.remaining_steps) == 6
        assert info.progress_percentage == 0.0

    def test_get_workflow_info_from_transcribed(self, state_machine, sample_episode):
        """
        Given: Episode with workflow_status=TRANSCRIBED
        When: Calling get_workflow_info()
        Then: Returns WorkflowInfo with 2 completed steps
        """
        sample_episode.workflow_status = WorkflowStatus.TRANSCRIBED
        info = state_machine.get_workflow_info(sample_episode)

        assert info.episode_id == sample_episode.id
        assert info.current_status == WorkflowStatus.TRANSCRIBED
        assert len(info.completed_steps) == 2
        assert "下载音频" in info.completed_steps
        assert "转录字幕" in info.completed_steps
        assert len(info.remaining_steps) == 4
        assert info.progress_percentage == pytest.approx(2.0 / 6.0 * 100)

    def test_get_workflow_info_from_ready_for_review(self, state_machine, sample_episode):
        """
        Given: Episode with workflow_status=READY_FOR_REVIEW
        When: Calling get_workflow_info()
        Then: Returns WorkflowInfo with all steps completed
        """
        sample_episode.workflow_status = WorkflowStatus.READY_FOR_REVIEW
        info = state_machine.get_workflow_info(sample_episode)

        assert info.episode_id == sample_episode.id
        assert info.current_status == WorkflowStatus.READY_FOR_REVIEW
        assert len(info.completed_steps) == 6
        assert len(info.remaining_steps) == 0
        assert info.progress_percentage == 100.0

    def test_get_workflow_info_step_labels_are_chinese(self, state_machine, sample_episode):
        """
        Given: Episode at any status
        When: Calling get_workflow_info()
        Then: All step labels are in Chinese
        """
        sample_episode.workflow_status = WorkflowStatus.SEGMENTED
        info = state_machine.get_workflow_info(sample_episode)

        all_steps = info.completed_steps + info.remaining_steps
        for step in all_steps:
            assert any(ord(c) > 127 for c in step), f"Step '{step}' should contain Chinese characters"
