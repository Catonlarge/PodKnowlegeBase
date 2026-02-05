"""
Workflow Status Enumeration

Defines the 8-state workflow for Episode processing.
"""
from enum import IntEnum


class WorkflowStatus(IntEnum):
    """
    Episode workflow status enumeration.

    The workflow progresses through these states:
    0. INIT - URL recorded in database
    1. DOWNLOADED - Audio file downloaded locally
    2. TRANSCRIBED - WhisperX transcription completed
    3. PROOFREAD - LLM subtitle proofreading completed
    4. SEGMENTED - AI semantic chapter segmentation completed
    5. TRANSLATED - All translations completed
    6. READY_FOR_REVIEW - Obsidian document generated
    7. PUBLISHED - Distributed to platforms
    """

    INIT = 0
    DOWNLOADED = 1
    TRANSCRIBED = 2
    PROOFREAD = 3
    SEGMENTED = 4
    TRANSLATED = 5
    READY_FOR_REVIEW = 6
    PUBLISHED = 7

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
            3: "已校对",
            4: "已分章",
            5: "已翻译",
            6: "待审核",
            7: "已发布",
        }
        return labels.get(self.value, "未知状态")
