"""
Main Workflow Runner

Orchestrates the complete workflow from YouTube URL to Obsidian document.
Supports checkpoint resume and progress visualization.
"""
import hashlib
from typing import Optional

from sqlalchemy.orm import Session
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn
from rich.panel import Panel
from rich.table import Table

from app.enums.workflow_status import WorkflowStatus
from app.models import Episode, Chapter, TranscriptCue, AudioSegment
from app.workflows.state_machine import (
    WorkflowStateMachine,
    WorkflowInfo,
    StepFunction,
)
from app.services.download_service import DownloadService
from app.services.transcription_service import TranscriptionService
from app.services.subtitle_proofreading_service import SubtitleProofreadingService
from app.services.segmentation_service import SegmentationService
from app.services.translation_service import TranslationService
from app.services.obsidian_service import ObsidianService


def calculate_url_hash(url: str) -> str:
    """
    Calculate MD5 hash of URL for deduplication.

    Args:
        url: URL string

    Returns:
        MD5 hash hex string
    """
    return hashlib.md5(url.encode()).hexdigest()


def create_or_get_episode(db: Session, url: str, force_restart: bool = False) -> Episode:
    """
    Create new episode or get existing one by URL.

    Args:
        db: Database session
        url: YouTube URL
        force_restart: If True, reset status to INIT

    Returns:
        Episode object
    """
    # Use local calculate_url_hash function
    file_hash = calculate_url_hash(url)

    # Try to find existing episode
    episode = db.query(Episode).filter(
        Episode.file_hash == file_hash
    ).first()

    if episode:
        if force_restart:
            episode.workflow_status = WorkflowStatus.INIT
            db.commit()
            db.refresh(episode)
        return episode

    # Create new episode with required defaults
    # Duration will be updated when audio is downloaded
    episode = Episode(
        title="",  # Will be updated from metadata
        file_hash=file_hash,
        source_url=url,
        duration=0.0,  # Required field, will be updated later
        workflow_status=WorkflowStatus.INIT,
    )
    db.add(episode)
    db.commit()
    db.refresh(episode)

    return episode


class WorkflowRunner:
    """
    Main workflow runner for Episode processing.

    Orchestrates all workflow steps from download to document generation.
    Supports checkpoint resume for long-running workflows.
    """

    def __init__(self, db: Session, console: Optional[Console] = None):
        """
        Initialize workflow runner.

        Args:
            db: Database session
            console: Rich Console for output (creates new one if None)
        """
        self.db = db
        self.console = console or Console()
        self.state_machine = WorkflowStateMachine(db)

    def run_workflow(self, url: str, force_restart: bool = False, force_resegment: bool = False) -> Episode:
        """
        Execute the complete workflow from URL to document.

        Args:
            url: YouTube URL
            force_restart: Force restart from beginning
            force_resegment: Force re-segment (clear old chapters and re-run AI)

        Returns:
            Processed Episode object
        """
        # Get or create episode
        episode = create_or_get_episode(self.db, url, force_restart)

        # Force re-segment: clear old chapters and reset to PROOFREAD
        if force_resegment and episode.workflow_status >= WorkflowStatus.SEGMENTED.value:
            cues = (
                self.db.query(TranscriptCue)
                .join(AudioSegment, AudioSegment.id == TranscriptCue.segment_id)
                .filter(AudioSegment.episode_id == episode.id)
            ).all()
            for cue in cues:
                cue.chapter_id = None
            self.db.query(Chapter).filter(Chapter.episode_id == episode.id).delete(
                synchronize_session=False
            )
            episode.workflow_status = WorkflowStatus.PROOFREAD.value
            self.db.commit()
            self.db.refresh(episode)
            self.console.print("[yellow]已清除旧章节，将强制重新切分[/yellow]")

        # Check if can resume
        can_resume, message = self.state_machine.can_resume(episode)
        if can_resume and not force_restart:
            self.console.print(f"[yellow]⚠ {message}[/yellow]")

        # Process steps until complete
        while True:
            next_step = self.state_machine.get_next_step(episode)
            if next_step is None:
                break

            # Execute step
            episode = self._run_step(next_step, episode)

            # Refresh from database
            self.db.refresh(episode)

        return episode

    def _run_step(self, step_func: StepFunction, episode: Episode) -> Episode:
        """
        Execute a single workflow step.

        Args:
            step_func: Step function to execute
            episode: Episode to process

        Returns:
            Updated Episode
        """
        # Get function name, handling Mock objects
        step_name = getattr(step_func, "__name__", str(step_func))
        self.console.print(f"[cyan]执行步骤: {step_name}[/cyan]")

        # Execute the step
        result = step_func(episode, self.db)

        # Check if result is persistent before refreshing
        if result in self.db:
            self.db.refresh(result)

        return result

    def _display_progress(self, workflow_info: WorkflowInfo):
        """
        Display workflow progress panel.

        Args:
            workflow_info: Workflow information to display
        """
        # Create progress table
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Label", style="bold cyan")
        table.add_column("Value")

        table.add_row("任务 ID", str(workflow_info.episode_id))
        table.add_row("当前状态", workflow_info.current_status.label)
        table.add_row("进度", f"[{workflow_info.progress_percentage:.1f}%]")

        # Build completed steps string
        if workflow_info.completed_steps:
            completed_str = "\n".join(f"  ✓ {step}" for step in workflow_info.completed_steps)
        else:
            completed_str = "  (无)"

        # Build remaining steps string
        if workflow_info.remaining_steps:
            remaining_str = "\n".join(f"  ○ {step}" for step in workflow_info.remaining_steps)
        else:
            remaining_str = "  (无)"

        table.add_row("已完成", completed_str)
        table.add_row("待执行", remaining_str)

        panel = Panel(
            table,
            title="[bold blue]EnglishPod3 Enhanced - 主工作流[/bold blue]",
            border_style="blue",
        )

        self.console.print(panel)


# Step processing functions


def download_episode(episode: Episode, db: Session) -> Episode:
    """
    Download audio file for episode.

    Args:
        episode: Episode to process
        db: Database session

    Returns:
        Updated Episode with DOWNLOADED status
    """
    service = DownloadService(db)
    local_path, metadata = service.download(episode.source_url)

    episode.audio_path = local_path
    episode.title = metadata.get("title") or episode.title or "Unknown Title"
    episode.duration = metadata.get("duration") or episode.duration or 0
    episode.workflow_status = WorkflowStatus.DOWNLOADED
    db.commit()

    return episode


def transcribe_episode(episode: Episode, db: Session) -> Episode:
    """
    Transcribe audio to text using WhisperX.

    Args:
        episode: Episode to process
        db: Database session

    Returns:
        Updated Episode with TRANSCRIBED status
    """
    service = TranscriptionService(db)
    service.segment_and_transcribe(episode.id)

    episode.workflow_status = WorkflowStatus.TRANSCRIBED
    db.commit()

    return episode


def proofread_episode(episode: Episode, db: Session) -> Episode:
    """
    Proofread subtitles using LLM.

    Args:
        episode: Episode to process
        db: Database session

    Returns:
        Updated Episode with PROOFREAD status
    """
    service = SubtitleProofreadingService(db, provider="moonshot")
    service.scan_and_correct(episode.id, apply=True)

    episode.workflow_status = WorkflowStatus.PROOFREAD
    db.commit()

    return episode


def segment_episode(episode: Episode, db: Session) -> Episode:
    """
    Segment transcript into semantic chapters.

    Args:
        episode: Episode to process
        db: Database session

    Returns:
        Updated Episode with SEGMENTED status
    """
    service = SegmentationService(db, provider="moonshot")
    service.analyze_and_segment(episode.id)

    episode.workflow_status = WorkflowStatus.SEGMENTED
    db.commit()

    return episode


def translate_episode(episode: Episode, db: Session) -> Episode:
    """
    Translate transcript cues to target language.

    TranslationService 仅在全部 cue 翻译完成时更新为 TRANSLATED，
    未完成时保持 SEGMENTED 以支持断点续传。

    Args:
        episode: Episode to process
        db: Database session

    Returns:
        Updated Episode (TRANSLATED if all done, else SEGMENTED)
    """
    service = TranslationService(db, provider="moonshot")
    service.batch_translate(episode.id, language_code="zh")

    db.refresh(episode)  # 使用 TranslationService 更新的状态
    db.commit()

    return episode


def generate_obsidian_doc(episode: Episode, db: Session) -> Episode:
    """
    Generate Obsidian markdown document.

    仅当翻译已全部完成 (status >= TRANSLATED) 时才推进到 READY_FOR_REVIEW。

    Args:
        episode: Episode to process
        db: Database session

    Returns:
        Updated Episode (READY_FOR_REVIEW if translation complete)
    """
    service = ObsidianService(db)
    service.render_episode(episode.id)

    if episode.workflow_status >= WorkflowStatus.TRANSLATED.value:
        episode.workflow_status = WorkflowStatus.READY_FOR_REVIEW
    db.commit()

    return episode


# Export step functions for state machine
__all__ = [
    "WorkflowRunner",
    "create_or_get_episode",
    "download_episode",
    "transcribe_episode",
    "proofread_episode",
    "segment_episode",
    "translate_episode",
    "generate_obsidian_doc",
]
