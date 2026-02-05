"""
Workflow State Machine

Manages the workflow state transitions for Episode processing.
Provides resume capability and workflow progress information.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Callable

from sqlalchemy.orm import Session

from app.enums.workflow_status import WorkflowStatus
from app.models import Episode


# Step function type hint
StepFunction = Callable[[Episode, Session], Episode]


@dataclass
class WorkflowInfo:
    """Workflow information container"""

    episode_id: int
    current_status: WorkflowStatus
    completed_steps: List[str] = field(default_factory=list)
    remaining_steps: List[str] = field(default_factory=list)
    progress_percentage: float = 0.0


class WorkflowStateMachine:
    """
    Workflow state machine for Episode processing.

    Manages state transitions and provides resume capability
    for long-running workflow processes.
    """

    # Define all workflow steps with their labels
    _WORKFLOW_STEPS = {
        WorkflowStatus.INIT: ("app.workflows.runner.download_episode", "下载音频"),
        WorkflowStatus.DOWNLOADED: ("app.workflows.runner.transcribe_episode", "转录字幕"),
        WorkflowStatus.TRANSCRIBED: ("app.workflows.runner.proofread_episode", "校对字幕"),
        WorkflowStatus.PROOFREAD: ("app.workflows.runner.segment_episode", "语义分章"),
        WorkflowStatus.SEGMENTED: ("app.workflows.runner.translate_episode", "逐句翻译"),
        WorkflowStatus.TRANSLATED: ("app.workflows.runner.generate_obsidian_doc", "生成文档"),
    }

    def __init__(self, db: Session):
        """
        Initialize state machine.

        Args:
            db: Database session
        """
        self.db = db

    def get_next_step(self, episode: Episode) -> Optional[StepFunction]:
        """
        Get the next processing step for an episode.

        Args:
            episode: Episode object

        Returns:
            StepFunction or None if workflow is complete
        """
        current_status = episode.workflow_status

        # Check if workflow is complete
        if current_status >= WorkflowStatus.READY_FOR_REVIEW:
            return None

        # Get next step function path
        step_path = self._WORKFLOW_STEPS.get(current_status)
        if not step_path:
            return None

        # Dynamically import the function
        module_path, func_name = step_path[0].rsplit(".", 1)
        module = __import__(module_path, fromlist=[func_name])
        return getattr(module, func_name)

    def can_resume(self, episode: Episode) -> tuple[bool, str]:
        """
        Check if an episode can resume from its current state.

        Args:
            episode: Episode object

        Returns:
            Tuple of (can_resume: bool, message: str)
        """
        current_status = episode.workflow_status

        # Convert int to WorkflowStatus if needed
        if isinstance(current_status, int):
            current_status = WorkflowStatus(current_status)

        if current_status == WorkflowStatus.INIT:
            return False, "新任务，从头开始"

        if current_status >= WorkflowStatus.PUBLISHED:
            return False, "任务已完成"

        # Intermediate state - can resume
        status_label = current_status.label
        next_step = self.get_next_step(episode)
        if next_step:
            next_step_name = next_step.__name__
            # Get Chinese label for next step
            for step_info in self._WORKFLOW_STEPS.values():
                if next_step_name in step_info[0]:
                    return True, f"检测到历史任务: {status_label}，将从「{step_info[1]}」继续"
            return True, f"检测到历史任务: {status_label}"

        return False, "未知状态"

    def get_workflow_info(self, episode: Episode) -> WorkflowInfo:
        """
        Get comprehensive workflow information for an episode.

        Args:
            episode: Episode object

        Returns:
            WorkflowInfo with current status and steps
        """
        current_status = episode.workflow_status

        # Build completed steps list
        completed_steps = []
        for status, (func_path, label) in self._WORKFLOW_STEPS.items():
            if status < current_status:
                completed_steps.append(label)

        # Build remaining steps list
        # Include current step and all future steps
        remaining_steps = []
        for status, (func_path, label) in self._WORKFLOW_STEPS.items():
            if status >= current_status:
                remaining_steps.append(label)

        # Calculate progress percentage
        # When READY_FOR_REVIEW or beyond, all steps are complete
        if current_status >= WorkflowStatus.READY_FOR_REVIEW:
            completed_steps = [label for _, (_, label) in self._WORKFLOW_STEPS.items()]
            remaining_steps = []
            progress_percentage = 100.0
        else:
            total_steps = len(self._WORKFLOW_STEPS)
            completed_count = len(completed_steps)
            progress_percentage = (completed_count / total_steps) * 100 if total_steps > 0 else 0

        return WorkflowInfo(
            episode_id=episode.id,
            current_status=current_status,
            completed_steps=completed_steps,
            remaining_steps=remaining_steps,
            progress_percentage=progress_percentage
        )
