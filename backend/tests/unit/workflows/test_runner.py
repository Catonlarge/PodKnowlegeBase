"""
WorkflowRunner Unit Tests
"""
from unittest.mock import Mock, patch, MagicMock, PropertyMock
from datetime import datetime

import pytest
from rich.console import Console

from app.database import get_session
from app.enums.workflow_status import WorkflowStatus
from app.models import Episode, AudioSegment
from app.workflows.runner import (
    WorkflowRunner,
    download_episode,
    transcribe_episode,
    proofread_episode,
    segment_episode,
    translate_episode,
    generate_obsidian_doc,
)


@pytest.fixture(scope="function")
def runner(test_session):
    """Create WorkflowRunner instance"""
    console = Console()
    return WorkflowRunner(test_session, console)


@pytest.fixture(scope="function")
def sample_episode(test_session):
    """Create test Episode"""
    episode = Episode(
        title="Test Episode",
        file_hash="test_runner_001",
        source_url="https://www.youtube.com/watch?v=test001",
        duration=300.0,
        workflow_status=WorkflowStatus.INIT,
    )
    test_session.add(episode)
    test_session.commit()
    test_session.refresh(episode)
    return episode


@pytest.fixture(scope="function")
def sample_downloaded_episode(test_session):
    """Create test Episode with DOWNLOADED status"""
    episode = Episode(
        title="Downloaded Episode",
        file_hash="test_runner_002",
        source_url="https://www.youtube.com/watch?v=test002",
        duration=300.0,
        workflow_status=WorkflowStatus.DOWNLOADED,
        audio_path="D:/test/audio_002.mp3",
    )
    test_session.add(episode)
    test_session.commit()
    test_session.refresh(episode)
    return episode


class TestWorkflowRunnerInit:
    """Test WorkflowRunner initialization"""

    def test_init_with_db_and_console(self, test_session):
        """
        Given: Database session and Console
        When: Creating WorkflowRunner
        Then: Instance is created with correct attributes
        """
        console = Console()
        runner = WorkflowRunner(test_session, console)

        assert runner.db == test_session
        assert runner.console == console
        assert runner.state_machine is not None

    def test_init_with_default_console(self, test_session):
        """
        Given: Database session only
        When: Creating WorkflowRunner without console
        Then: Instance creates its own Console
        """
        runner = WorkflowRunner(test_session)

        assert runner.db == test_session
        assert runner.console is not None
        assert runner.state_machine is not None


class TestRunWorkflow:
    """Test run_workflow method"""

    @patch('app.workflows.runner.download_episode')
    def test_run_workflow_calls_next_step(self, mock_download, runner, sample_episode):
        """
        Given: Episode with workflow_status=INIT
        When: Calling run_workflow()
        Then: Calls next step function
        """
        # Mock to stop after one step
        mock_download.return_value = sample_episode

        with patch.object(runner.state_machine, 'get_next_step', side_effect=[mock_download, None]):
            result = runner.run_workflow(sample_episode.source_url)

            assert mock_download.called

    @patch('app.workflows.runner.transcribe_episode')
    def test_run_workflow_resumes_from_downloaded(self, mock_transcribe, runner, sample_downloaded_episode):
        """
        Given: Episode with workflow_status=DOWNLOADED
        When: Calling run_workflow()
        Then: Starts from transcribe step
        """
        # Mock to stop after one step
        mock_transcribe.return_value = sample_downloaded_episode

        with patch.object(runner.state_machine, 'get_next_step', side_effect=[mock_transcribe, None]):
            result = runner.run_workflow(sample_downloaded_episode.source_url)

            assert mock_transcribe.called

    def test_run_workflow_with_no_steps_returns_episode(self, runner, sample_episode):
        """
        Given: Episode with READY_FOR_REVIEW status
        When: Calling run_workflow()
        Then: Returns episode without processing
        """
        sample_episode.workflow_status = WorkflowStatus.READY_FOR_REVIEW
        runner.db.commit()

        # Mock create_or_get_episode to return the existing episode
        with patch.object(runner.state_machine, 'get_next_step', return_value=None):
            with patch('app.workflows.runner.create_or_get_episode', return_value=sample_episode):
                result = runner.run_workflow(sample_episode.source_url)

                assert result.id == sample_episode.id

    def test_run_workflow_duplicate_url_returns_existing(self, runner, sample_episode):
        """
        Given: Existing URL in database
        When: Calling run_workflow() with same URL
        Then: Returns existing episode
        """
        sample_episode.workflow_status = WorkflowStatus.READY_FOR_REVIEW
        runner.db.commit()

        # Mock create_or_get_episode to return the existing episode
        with patch.object(runner.state_machine, 'get_next_step', return_value=None):
            with patch('app.workflows.runner.create_or_get_episode', return_value=sample_episode):
                result = runner.run_workflow(sample_episode.source_url)

                assert result.id == sample_episode.id


class TestRunStep:
    """Test _run_step method"""

    @patch('app.workflows.runner.download_episode')
    def test_run_step_updates_status(self, mock_download, runner, sample_episode):
        """
        Given: Step function and episode
        When: Calling _run_step()
        Then: Episode status is updated in database
        """
        # Make mock return the episode with updated status
        def update_status(ep, db):
            ep.workflow_status = WorkflowStatus.DOWNLOADED
            ep.audio_path = "/test/path.mp3"
            db.add(ep)
            db.commit()
            return ep

        mock_download.side_effect = update_status

        result = runner._run_step(mock_download, sample_episode)

        assert result.workflow_status == WorkflowStatus.DOWNLOADED

    @patch('app.workflows.runner.download_episode')
    def test_run_step_handles_exception(self, mock_download, runner, sample_episode):
        """
        Given: Step function that raises exception
        When: Calling _run_step()
        Then: Exception is propagated
        """
        mock_download.side_effect = Exception("Download failed")

        with pytest.raises(Exception, match="Download failed"):
            runner._run_step(mock_download, sample_episode)


class TestDisplayProgress:
    """Test _display_progress method"""

    def test_display_progress_shows_workflow_info(self, runner, sample_episode):
        """
        Given: WorkflowInfo object
        When: Calling _display_progress()
        Then: Console displays workflow information
        """
        from app.workflows.state_machine import WorkflowInfo

        info = WorkflowInfo(
            episode_id=sample_episode.id,
            current_status=WorkflowStatus.TRANSCRIBED,
            completed_steps=["下载音频", "转录字幕"],
            remaining_steps=["校对字幕", "语义分章", "逐句翻译", "生成文档"],
            progress_percentage=33.33
        )

        # Should not raise exception
        runner._display_progress(info)


class TestStepFunctions:
    """Test individual step functions"""

    @patch('app.workflows.runner.DownloadService')
    def test_download_episode_success(self, mock_service_cls, test_session, sample_episode):
        """
        Given: Episode with INIT status
        When: Calling download_episode()
        Then: Downloads audio and updates status to DOWNLOADED
        """
        mock_service = Mock()
        mock_service.download.return_value = "D:/test/audio.mp3"
        mock_service_cls.return_value = mock_service

        result = download_episode(sample_episode, test_session)

        assert result.workflow_status == WorkflowStatus.DOWNLOADED
        assert result.audio_path == "D:/test/audio.mp3"
        mock_service.download.assert_called_once()

    @patch('app.workflows.runner.TranscriptionService')
    def test_transcribe_episode_success(self, mock_service_cls, test_session, sample_downloaded_episode):
        """
        Given: Episode with DOWNLOADED status
        When: Calling transcribe_episode()
        Then: Transcribes audio and updates status to TRANSCRIBED
        """
        # Create audio segment for the episode
        segment = AudioSegment(
            episode_id=sample_downloaded_episode.id,
            segment_index=0,
            segment_id="seg_001",
            start_time=0.0,
            end_time=300.0
        )
        test_session.add(segment)
        test_session.commit()

        mock_service = Mock()
        mock_service.segment_and_transcribe.return_value = None
        mock_service_cls.return_value = mock_service

        result = transcribe_episode(sample_downloaded_episode, test_session)

        assert result.workflow_status == WorkflowStatus.TRANSCRIBED
        mock_service.segment_and_transcribe.assert_called_once()

    @patch('app.workflows.runner.SubtitleProofreadingService')
    def test_proofread_episode_success(self, mock_service_cls, test_session, sample_episode):
        """
        Given: Episode with TRANSCRIBED status
        When: Calling proofread_episode()
        Then: Proofreads subtitles and updates status to PROOFREAD
        """
        sample_episode.workflow_status = WorkflowStatus.TRANSCRIBED
        test_session.commit()

        mock_service = Mock()
        mock_service.scan_and_correct.return_value = Mock(corrected_count=0)
        mock_service_cls.return_value = mock_service

        result = proofread_episode(sample_episode, test_session)

        assert result.workflow_status == WorkflowStatus.PROOFREAD
        mock_service.scan_and_correct.assert_called_once()

    @patch('app.workflows.runner.SegmentationService')
    def test_segment_episode_success(self, mock_service_cls, test_session, sample_episode):
        """
        Given: Episode with PROOFREAD status
        When: Calling segment_episode()
        Then: Segments transcript and updates status to SEGMENTED
        """
        sample_episode.workflow_status = WorkflowStatus.PROOFREAD
        test_session.commit()

        mock_service = Mock()
        mock_service.analyze_and_segment.return_value = []
        mock_service_cls.return_value = mock_service

        result = segment_episode(sample_episode, test_session)

        assert result.workflow_status == WorkflowStatus.SEGMENTED
        mock_service.analyze_and_segment.assert_called_once()

    @patch('app.workflows.runner.TranslationService')
    def test_translate_episode_success(self, mock_service_cls, test_session, sample_episode):
        """
        Given: Episode with SEGMENTED status
        When: Calling translate_episode() and TranslationService 全部翻译完成
        Then: Status 由 TranslationService 更新为 TRANSLATED，runner 通过 refresh 获取
        """
        sample_episode.workflow_status = WorkflowStatus.SEGMENTED
        test_session.commit()

        def mock_batch_translate(episode_id, language_code="zh"):
            ep = test_session.get(Episode, episode_id)
            if ep:
                ep.workflow_status = WorkflowStatus.TRANSLATED.value
                test_session.flush()
            return 10

        mock_service = Mock()
        mock_service.batch_translate.side_effect = mock_batch_translate
        mock_service_cls.return_value = mock_service

        result = translate_episode(sample_episode, test_session)

        assert result.workflow_status == WorkflowStatus.TRANSLATED
        mock_service.batch_translate.assert_called_once()

    @patch('app.workflows.runner.TranslationService')
    def test_translate_episode_keeps_segmented_when_partial(
        self, mock_service_cls, test_session, sample_episode
    ):
        """
        Given: Episode with SEGMENTED status
        When: batch_translate 部分完成（TranslationService 不更新 status）
        Then: Status 保持 SEGMENTED
        """
        sample_episode.workflow_status = WorkflowStatus.SEGMENTED
        test_session.commit()

        mock_service = Mock()
        mock_service.batch_translate.return_value = 5  # 部分成功，不修改 episode
        mock_service_cls.return_value = mock_service

        result = translate_episode(sample_episode, test_session)

        assert result.workflow_status == WorkflowStatus.SEGMENTED
        mock_service.batch_translate.assert_called_once()

    @patch('app.workflows.runner.ObsidianService')
    def test_generate_obsidian_doc_success(self, mock_service_cls, test_session, sample_episode):
        """
        Given: Episode with TRANSLATED status (翻译已全部完成)
        When: Calling generate_obsidian_doc()
        Then: Generates Obsidian document and updates status to READY_FOR_REVIEW
        """
        sample_episode.workflow_status = WorkflowStatus.TRANSLATED
        test_session.commit()

        mock_service = Mock()
        mock_service.save_episode.return_value = Mock()
        mock_service_cls.return_value = mock_service

        result = generate_obsidian_doc(sample_episode, test_session)

        assert result.workflow_status == WorkflowStatus.READY_FOR_REVIEW
        mock_service.save_episode.assert_called_once_with(sample_episode.id, language_code="zh")

    @patch('app.workflows.runner.ObsidianService')
    def test_generate_obsidian_doc_keeps_segmented_when_translation_incomplete(
        self, mock_service_cls, test_session, sample_episode
    ):
        """
        Given: Episode with SEGMENTED status (翻译未完成)
        When: Calling generate_obsidian_doc()
        Then: Generates document but status stays SEGMENTED
        """
        sample_episode.workflow_status = WorkflowStatus.SEGMENTED
        test_session.commit()

        mock_service = Mock()
        mock_service.save_episode.return_value = Mock()
        mock_service_cls.return_value = mock_service

        result = generate_obsidian_doc(sample_episode, test_session)

        assert result.workflow_status == WorkflowStatus.SEGMENTED
        mock_service.save_episode.assert_called_once_with(sample_episode.id, language_code="zh")
