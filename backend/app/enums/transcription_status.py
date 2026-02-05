"""
Transcription Status Enumeration

Defines the status states for AudioSegment transcription.
"""
from enum import Enum


class TranscriptionStatus(str, Enum):
    """
    AudioSegment transcription status enumeration.

    Each segment goes through these states during transcription:
    - pending: Waiting to be transcribed
    - processing: Currently being transcribed by Whisper
    - completed: Transcription successful, segment_path deleted
    - failed: Transcription failed, segment_path retained for retry
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
            "pending": "等待转录",
            "processing": "转录中",
            "completed": "转录完成",
            "failed": "转录失败",
        }
        return labels.get(self.value, "未知状态")
