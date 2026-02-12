# End to End Workflow Test
"""
Integration tests for the complete workflow system.

Tests the orchestration logic of both main and publish workflows,
using mocks for external services (AI APIs, Publisher APIs).
"""
import hashlib
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, Episode, TranscriptCue, Translation, MarketingPost, PublicationRecord
from app.enums.workflow_status import WorkflowStatus
from app.workflows.state_machine import WorkflowStateMachine, WorkflowInfo
from app.workflows.runner import WorkflowRunner, calculate_url_hash
from app.workflows.publisher import WorkflowPublisher, Diff
from rich.console import Console


# =============================================================================
# Test Database Setup
# =============================================================================

@pytest.fixture(scope="function")
def test_db():
    """
    Create an in-memory SQLite database for testing.

    Yields:
        Session: SQLAlchemy session
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        yield session


@pytest.fixture(scope="function")
def test_console():
    """
    Create a test Rich console.

    Yields:
        Console: Rich console instance (uses stderr to avoid test output pollution)
    """
    # Use stderr for test output to avoid polluting stdout
    console = Console(stderr=True)
    yield console


# =============================================================================
# Helper Fixtures
# =============================================================================

@pytest.fixture(scope="function")
def sample_episode(test_db):
    """
    Create a sample episode with APPROVED status.

    Args:
        test_db: Test database session

    Yields:
        Episode: Sample episode ready for publishing
    """
    from app.models import AudioSegment

    episode = Episode(
        title="Test Episode",
        file_hash="abc123",
        source_url="https://example.com/video",
        duration=120.5,
        workflow_status=WorkflowStatus.APPROVED,
        ai_summary="This is a test episode summary."
    )
    test_db.add(episode)
    test_db.flush()

    # Create an audio segment for cues
    segment = AudioSegment(
        episode_id=episode.id,
        segment_index=0,
        segment_id="segment_001",
        start_time=0.0,
        end_time=30.0
    )
    test_db.add(segment)
    test_db.flush()

    # Add some cues
    for i in range(3):
        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=float(i * 10),
            end_time=float((i + 1) * 10),
            text=f"Test sentence {i}"
        )
        test_db.add(cue)

    # Add translations
    test_db.flush()
    cues = test_db.query(TranscriptCue).filter(TranscriptCue.segment_id == segment.id).all()
    for cue in cues:
        translation = Translation(
            cue_id=cue.id,
            language_code="zh",
            translation=f"Translation for {cue.text}"
        )
        test_db.add(translation)

    test_db.commit()
    yield episode


# =============================================================================
# State Machine Integration Tests
# =============================================================================

def test_state_machine_workflow_progress_tracking(test_db):
    """
    Behavior: State machine tracks workflow progress correctly

    Given:
        - A new episode with INIT status
    When:
        - Getting workflow info
    Then:
        - Should show 0 completed steps
        - Should show 6 remaining steps
        - Progress should be 0%
    """
    episode = Episode(
        title="Test",
        file_hash="hash1",
        source_url="https://test.com",
        duration=0.0,
        workflow_status=WorkflowStatus.INIT
    )
    test_db.add(episode)
    test_db.flush()

    state_machine = WorkflowStateMachine(test_db)
    info = state_machine.get_workflow_info(episode)

    assert info.episode_id == episode.id
    assert info.current_status == WorkflowStatus.INIT
    assert len(info.completed_steps) == 0
    assert len(info.remaining_steps) == 6
    assert info.progress_percentage == 0.0


def test_state_machine_half_progress_tracking(test_db):
    """
    Behavior: State machine calculates progress for half-completed workflow

    Given:
        - An episode with TRANSCRIBED status (2 steps completed)
    When:
        - Getting workflow info
    Then:
        - Should show 2 completed steps
        - Should show 4 remaining steps
        - Progress should be approximately 33%
    """
    episode = Episode(
        title="Test",
        file_hash="hash2",
        source_url="https://test.com",
        duration=0.0,
        workflow_status=WorkflowStatus.TRANSCRIBED
    )
    test_db.add(episode)
    test_db.flush()

    state_machine = WorkflowStateMachine(test_db)
    info = state_machine.get_workflow_info(episode)

    assert len(info.completed_steps) == 2
    assert len(info.remaining_steps) == 4
    assert info.progress_percentage == pytest.approx(33.33, rel=1e-2)


def test_state_machine_completed_workflow(test_db):
    """
    Behavior: State machine shows 100% progress for completed workflow

    Given:
        - An episode with READY_FOR_REVIEW status
    When:
        - Getting workflow info
    Then:
        - Should show all 6 steps completed
        - Should show 0 remaining steps
        - Progress should be 100%
    """
    episode = Episode(
        title="Test",
        file_hash="hash3",
        source_url="https://test.com",
        duration=0.0,
        workflow_status=WorkflowStatus.READY_FOR_REVIEW
    )
    test_db.add(episode)
    test_db.flush()

    state_machine = WorkflowStateMachine(test_db)
    info = state_machine.get_workflow_info(episode)

    assert len(info.completed_steps) == 6
    assert len(info.remaining_steps) == 0
    assert info.progress_percentage == 100.0


# =============================================================================
# Publisher Workflow Integration Tests (with Mocks)
# =============================================================================

def test_publisher_parse_and_backfill_no_changes(test_db, sample_episode, test_console):
    """
    Behavior: Publisher detects no changes when Obsidian document matches database

    Given:
        - An episode with READY_FOR_REVIEW status
        - Obsidian document does not exist
    When:
        - Running parse_and_backfill
    Then:
        - Should return empty list of diffs
        - Should not modify any translations
    """
    # Create publisher and mock the obsidian service
    publisher = WorkflowPublisher(test_db, test_console)

    # Mock the obsidian service at instance level
    mock_obsidian = Mock()
    mock_obsidian._get_episode_path.return_value = Path("/nonexistent/path")
    publisher.obsidian_service = mock_obsidian

    diffs = publisher.parse_and_backfill(sample_episode)

    assert len(diffs) == 0


def test_publisher_parse_and_backfill_with_changes(test_db, sample_episode, test_console):
    """
    Behavior: Publisher detects and backfills translation changes from Obsidian

    Given:
        - An episode with READY_FOR_REVIEW status
        - Obsidian document has translation edits
    When:
        - Running parse_and_backfill
    Then:
        - Should detect all changes
        - Should update database with new translations
        - Should mark translations as edited
    """
    # Get original translation
    original_translation = test_db.query(Translation).first()
    original_text = original_translation.translation

    # Create publisher and mock obsidian service
    publisher = WorkflowPublisher(test_db, test_console)

    # Create a mock path that "exists"
    mock_path = Mock(spec=Path)
    mock_path.exists.return_value = True
    mock_obsidian = Mock()
    mock_obsidian._get_episode_path.return_value = mock_path
    mock_obsidian.parse_episode.return_value = {
        "translations": {
            original_translation.cue_id: "Edited translation text"
        }
    }
    publisher.obsidian_service = mock_obsidian

    diffs = publisher.parse_and_backfill(sample_episode)

    # Verify diffs detected
    assert len(diffs) == 1
    assert diffs[0].cue_id == original_translation.cue_id
    assert diffs[0].field == "translation"
    assert diffs[0].original_value == original_text
    assert diffs[0].new_value == "Edited translation text"

    # Verify database updated
    test_db.refresh(original_translation)
    assert original_translation.translation == "Edited translation text"
    assert original_translation.is_edited is True


def test_publisher_generate_marketing_without_llm(test_db, sample_episode, test_console):
    """
    Behavior: Publisher skips marketing generation when LLM not configured

    Given:
        - An episode with READY_FOR_REVIEW status
        - LLM service is not configured (MOONSHOT_API_KEY is None)
    When:
        - Running generate_marketing
    Then:
        - Should return empty list
        - Should not attempt to generate posts
    """
    with patch("app.workflows.publisher.MOONSHOT_API_KEY", None):
        publisher = WorkflowPublisher(test_db, test_console)
        posts = publisher.generate_marketing(sample_episode)

        assert posts == []


def test_publisher_generate_marketing_with_llm(test_db, sample_episode, test_console):
    """
    Behavior: Publisher generates marketing posts using LLM service

    Given:
        - An episode with READY_FOR_REVIEW status
        - LLM service is configured
    When:
        - Running generate_marketing
    Then:
        - Should call marketing service
        - Should return generated posts
    """
    # Mock marketing service
    mock_posts = [
        MarketingPost(
            episode_id=sample_episode.id,
            angle_tag="educational",
            content="Educational post content"
        ),
        MarketingPost(
            episode_id=sample_episode.id,
            angle_tag="humor",
            content="Humorous post content"
        )
    ]

    publisher = WorkflowPublisher(test_db, test_console)

    mock_marketing = Mock()
    mock_marketing.generate_posts.return_value = mock_posts
    publisher.marketing_service = mock_marketing

    posts = publisher.generate_marketing(sample_episode)

    assert len(posts) == 2
    assert posts[0].angle_tag == "educational"
    assert posts[1].angle_tag == "humor"
    mock_marketing.generate_posts.assert_called_once_with(sample_episode.id)


def test_publisher_distribute_to_platforms_all_success(test_db, sample_episode, test_console):
    """
    Behavior: Publisher successfully distributes to all platforms

    Given:
        - An episode with marketing posts
        - All publishers return success
    When:
        - Running distribute_to_platforms
    Then:
        - Should call all publishers
        - Should create success publication records
    """
    posts = [
        MarketingPost(
            episode_id=sample_episode.id,
            angle_tag="test",
            content="Test post"
        )
    ]

    # Mock all publishers to return success
    mock_feishu = Mock()
    mock_feishu.publish.return_value = PublicationRecord(
        episode_id=sample_episode.id,
        platform="feishu",
        status="success",
        platform_record_id="feishu123"
    )

    mock_ima = Mock()
    mock_ima.publish.return_value = PublicationRecord(
        episode_id=sample_episode.id,
        platform="ima",
        status="success",
        platform_record_id="ima456"
    )

    mock_marketing = Mock()
    mock_marketing.publish.return_value = PublicationRecord(
        episode_id=sample_episode.id,
        platform="marketing",
        status="success",
        platform_record_id="marketing789"
    )

    publisher = WorkflowPublisher(test_db, test_console)
    publisher.publishers = {
        "feishu": mock_feishu,
        "ima": mock_ima,
        "marketing": mock_marketing
    }

    records = publisher.distribute_to_platforms(sample_episode, posts)

    assert len(records) == 3
    assert all(r.status == "success" for r in records)
    assert records[0].platform == "feishu"
    assert records[1].platform == "ima"
    assert records[2].platform == "marketing"


def test_publisher_distribute_to_platforms_partial_failure(test_db, sample_episode, test_console):
    """
    Behavior: Publisher handles partial failures gracefully

    Given:
        - An episode with marketing posts
        - One publisher fails with exception
    When:
        - Running distribute_to_platforms
    Then:
        - Should continue with other publishers
        - Should create failure record for failed publisher
        - Should create success records for successful publishers
    """
    posts = [
        MarketingPost(
            episode_id=sample_episode.id,
            angle_tag="test",
            content="Test post"
        )
    ]

    # Mock publishers: feishu fails, others succeed
    mock_feishu = Mock()
    mock_feishu.publish.side_effect = Exception("Feishu API error")

    mock_ima = Mock()
    mock_ima.publish.return_value = PublicationRecord(
        episode_id=sample_episode.id,
        platform="ima",
        status="success",
        platform_record_id="ima123"
    )

    publisher = WorkflowPublisher(test_db, test_console)
    publisher.publishers = {
        "feishu": mock_feishu,
        "ima": mock_ima
    }

    records = publisher.distribute_to_platforms(sample_episode, posts)

    assert len(records) == 2
    assert records[0].status == "failed"
    assert records[0].error_message == "Feishu API error"
    assert records[1].status == "success"


def test_publisher_full_workflow_mocked(test_db, sample_episode, test_console):
    """
    Behavior: Full publish workflow completes end-to-end with mocked services

    Given:
        - An episode with APPROVED status
        - All external services mocked
    When:
        - Running publish_workflow
    Then:
        - Should complete all two steps (marketing + distribution)
        - Should update episode status to PUBLISHED
        - Should return updated episode
    """
    publisher = WorkflowPublisher(test_db, test_console)

    # Mock obsidian service (no changes)
    mock_obsidian = Mock()
    mock_obsidian._get_episode_path.return_value = Path("/fake/path")
    mock_obsidian.parse_episode.return_value = {"translations": {}}
    publisher.obsidian_service = mock_obsidian

    # Mock marketing service (generate posts)
    mock_posts = [
        MarketingPost(
            episode_id=sample_episode.id,
            angle_tag="test",
            content="Test post"
        )
    ]

    mock_marketing = Mock()
    mock_marketing.generate_posts.return_value = mock_posts
    publisher.marketing_service = mock_marketing

    # Mock publishers (all succeed)
    mock_publisher = Mock()
    mock_publisher.publish.return_value = PublicationRecord(
        episode_id=sample_episode.id,
        platform="test_platform",
        status="success",
        platform_record_id="test123"
    )

    publisher.publishers = {"test": mock_publisher}

    result = publisher.publish_workflow(sample_episode.id)

    assert result.workflow_status == WorkflowStatus.PUBLISHED
    assert result.id == sample_episode.id


# =============================================================================
# Runner Workflow Integration Tests (with Mocks)
# =============================================================================

def test_runner_creates_new_episode(test_db, test_console):
    """
    Behavior: Runner creates new episode for new URL

    Given:
        - A new YouTube URL
        - No existing episode with same URL hash
    When:
        - Running run_workflow
    Then:
        - Should create new episode
        - Should set status to INIT
    """
    test_url = "https://youtube.com/watch?v=test123"

    with patch("app.workflows.runner.download_episode") as mock_download:
        mock_download.return_value = Episode(
            title="Test Episode",
            file_hash="hash",
            source_url=test_url,
            duration=100.0,
            workflow_status=WorkflowStatus.DOWNLOADED
        )

        with patch("app.workflows.runner.transcribe_episode"):
            with patch("app.workflows.runner.proofread_episode"):
                with patch("app.workflows.runner.segment_episode"):
                    with patch("app.workflows.runner.translate_episode"):
                        with patch("app.workflows.runner.generate_obsidian_doc"):
                            runner = WorkflowRunner(test_db, test_console)

                            # Mock state machine to stop immediately
                            runner.state_machine.get_next_step = Mock(return_value=None)
                            result = runner.run_workflow(test_url)

                            assert result.source_url == test_url
                            assert result.file_hash is not None


def test_runner_resumes_existing_episode(test_db, test_console):
    """
    Behavior: Runner resumes from checkpoint for existing episode

    Given:
        - An existing episode with DOWNLOADED status
        - Same URL provided
    When:
        - Running run_workflow without --restart
    Then:
        - Should resume from transcribe step
        - Should NOT create new episode
    """
    test_url = "https://youtube.com/watch?v=test456"
    test_hash = calculate_url_hash(test_url)

    # Create existing episode with actual hash
    existing = Episode(
        title="Existing Episode",
        file_hash=test_hash,
        source_url=test_url,
        duration=50.0,
        workflow_status=WorkflowStatus.DOWNLOADED
    )
    test_db.add(existing)
    test_db.commit()

    with patch("app.workflows.runner.transcribe_episode") as mock_transcribe:
        mock_transcribe.return_value = existing

        with patch("app.workflows.runner.proofread_episode"):
            with patch("app.workflows.runner.segment_episode"):
                with patch("app.workflows.runner.translate_episode"):
                    with patch("app.workflows.runner.generate_obsidian_doc"):
                        runner = WorkflowRunner(test_db, test_console)

                        # Mock state machine to stop immediately
                        runner.state_machine.get_next_step = Mock(return_value=None)
                        result = runner.run_workflow(test_url)

                        assert result.id == existing.id
                        assert result.workflow_status == WorkflowStatus.DOWNLOADED


def test_runner_force_restart(test_db, test_console):
    """
    Behavior: Runner restarts workflow when --restart flag is set

    Given:
        - An existing episode with TRANSCRIBED status
        - Same URL provided with --restart flag
    When:
        - Running run_workflow with force_restart=True
    Then:
        - Should reset status to INIT
        - Should start from beginning
    """
    test_url = "https://youtube.com/watch?v=test789"
    test_hash = calculate_url_hash(test_url)

    # Create existing episode with actual hash
    existing = Episode(
        title="Existing Episode",
        file_hash=test_hash,
        source_url=test_url,
        duration=50.0,
        workflow_status=WorkflowStatus.TRANSCRIBED
    )
    test_db.add(existing)
    test_db.commit()

    with patch("app.workflows.runner.download_episode") as mock_download:
        mock_download.return_value = existing

        runner = WorkflowRunner(test_db, test_console)

        # Mock to stop immediately
        runner.state_machine.get_next_step = Mock(return_value=None)
        result = runner.run_workflow(test_url, force_restart=True)

        # Status should have been reset to INIT
        assert result.workflow_status == WorkflowStatus.INIT


# =============================================================================
# Diff Dataclass Tests
# =============================================================================

def test_diff_dataclass_creation():
    """
    Behavior: Diff dataclass stores change information correctly

    Given:
        - Cue ID, field name, original and new values
    When:
        - Creating Diff instance
    Then:
        - Should store all attributes correctly
    """
    diff = Diff(
        cue_id=123,
        field="translation",
        original_value="Original text",
        new_value="New text"
    )

    assert diff.cue_id == 123
    assert diff.field == "translation"
    assert diff.original_value == "Original text"
    assert diff.new_value == "New text"


# =============================================================================
# WorkflowInfo Dataclass Tests
# =============================================================================

def test_workflow_info_dataclass(test_db):
    """
    Behavior: WorkflowInfo stores workflow progress information

    Given:
        - Episode ID, status, and progress data
    When:
        - Creating WorkflowInfo instance
    Then:
        - Should store all attributes correctly
    """
    info = WorkflowInfo(
        episode_id=1,
        current_status=WorkflowStatus.READY_FOR_REVIEW,
        completed_steps=["Step 1", "Step 2"],
        remaining_steps=["Step 3"],
        progress_percentage=66.67
    )

    assert info.episode_id == 1
    assert info.current_status == WorkflowStatus.READY_FOR_REVIEW
    assert len(info.completed_steps) == 2
    assert len(info.remaining_steps) == 1
    assert info.progress_percentage == 66.67
