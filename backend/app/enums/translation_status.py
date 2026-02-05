"""
Translation Status Enumeration

Defines the status states for Translation processing.
"""
from enum import Enum


class TranslationStatus(str, Enum):
    """
    Translation status enumeration.

    Each translation goes through these states:
    - pending: Waiting to be translated
    - processing: Currently being translated by LLM
    - completed: Translation successful
    - failed: Translation failed, can be retried
    """

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

    @property
    def label(self) -> str:
        """
        Get human-readable label for the status.

        Returns:
            str: Chinese label for display
        """
        labels = {
            "pending": "等待翻译",
            "processing": "翻译中",
            "completed": "翻译完成",
            "failed": "翻译失败",
        }
        return labels.get(self.value, "未知状态")
