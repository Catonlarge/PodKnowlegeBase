"""
TranscriptCorrection Model

Stores LLM corrections to Whisper transcript.
Used for subtitle proofreading service.
"""
from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class TranscriptCorrection(Base, TimestampMixin):
    """
    Represents an LLM correction to Whisper transcript.

    This model stores corrections made to Whisper-transcribed text,
    serving as:
    1. Correction history tracking
    2. Training data collection
    3. Correction quality analysis

    Attributes:
        id: Primary key
        cue_id: Foreign key to TranscriptCue
        original_text: Original Whisper transcription
        corrected_text: LLM-corrected text
        reason: Correction reason (e.g., "拼写错误", "专有名词")
        confidence: Confidence score (0-1)
        ai_model: AI model used for correction
        applied: Whether correction was applied to TranscriptCue
    """
    __tablename__ = "transcript_corrections"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key
    cue_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("transcript_cues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Foreign key to TranscriptCue"
    )

    # Content
    original_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Original Whisper transcription"
    )
    corrected_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="LLM-corrected text"
    )
    reason: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        doc="Correction reason (e.g., '拼写错误', '专有名词', '连读误识别')"
    )
    confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        doc="Confidence score (0-1) from LLM"
    )
    ai_model: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        doc="AI model used for correction (e.g., 'moonshot-v1-8k')"
    )
    applied: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc="Whether correction was applied to TranscriptCue.corrected_text"
    )

    # Relationships
    cue = relationship("TranscriptCue", back_populates="transcript_corrections")

    __table_args__ = (
        Index("idx_transcript_corr_cue", "cue_id"),
    )

    def __repr__(self) -> str:
        return f"<TranscriptCorrection(id={self.id})>"
