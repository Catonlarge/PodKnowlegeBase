"""
Workflow Status Enumeration

Defines the 7-state workflow for Episode processing.
"""
from enum import IntEnum


class WorkflowStatus(IntEnum):
    """
    Episode workflow status enumeration.

    The workflow progresses through these states:
    0. INIT - URL recorded in database
    1. DOWNLOADED - Audio file downloaded locally
    2. TRANSCRIBED - WhisperX transcription completed
    3. SEGMENTED - AI semantic chapter segmentation completed
    4. TRANSLATED - All translations completed
    5. READY_FOR_REVIEW - Obsidian document generated
    6. PUBLISHED - Distributed to platforms
    """

    INIT = 0
    DOWNLOADED = 1
    TRANSCRIBED = 2
    SEGMENTED = 3
    TRANSLATED = 4
    READY_FOR_REVIEW = 5
    PUBLISHED = 6

    def get_next_status(self) -> "WorkflowStatus":
        """
        Get the next status in the workflow.

        Returns:
            WorkflowStatus: The next status, or self if already at PUBLISHED
        """
        next_value = self.value + 1
        if next_value <= WorkflowStatus.PUBLISHED.value:
            return WorkflowStatus(next_value)
        return self

    @property
    def label(self) -> str:
        """
        Get human-readable label for the status.

        Returns:
            str: Chinese label for display
        """
        labels = {
            0: "已初始化",
            1: "已下载",
            2: "已转录",
            3: "已分章",
            4: "已翻译",
            5: "待审核",
            6: "已发布",
        }
        return labels.get(self.value, "未知状态")
