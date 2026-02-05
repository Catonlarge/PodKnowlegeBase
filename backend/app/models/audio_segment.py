"""
AudioSegment Model

Represents a virtual audio segment for async transcription and resume capability.
"""
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums.transcription_status import TranscriptionStatus
from app.models.base import Base, TimestampMixin


class AudioSegment(Base, TimestampMixin):
    """
    Represents a virtual audio segment for transcription.

    This model supports:
    - Virtual segmentation without cutting physical files
    - Async transcription with interrupt recovery
    - Resume capability on failure

    Attributes:
        id: Primary key
        episode_id: Foreign key to Episode
        segment_index: Segment sequence number (0, 1, 2...)
        segment_id: Segment ID (e.g., "segment_001")
        segment_path: Temporary audio file path
        start_time: Start time in original audio (seconds)
        end_time: End time in original audio (seconds)
        status: Transcription status
        error_message: Error message if failed
        retry_count: Number of retries
        transcription_started_at: When transcription started
        recognized_at: When transcription completed

    Note: Relationships to TranscriptCue will be added after that model is created.
    """

    __tablename__ = "audio_segments"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key
    episode_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("episodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Foreign key to Episode"
    )

    # Segment identification
    segment_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Segment sequence number (0, 1, 2...)"
    )
    segment_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="Segment ID (e.g., 'segment_001')"
    )

    # File path (lifecycle: NULL -> has path -> NULL on completion)
    segment_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        doc="Temporary audio file path"
    )

    # Time range (absolute time from original audio)
    start_time: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        doc="Start time in original audio (seconds)"
    )
    end_time: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        doc="End time in original audio (seconds)"
    )

    # Transcription status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=TranscriptionStatus.PENDING.value,
        index=True,
        doc="Transcription status"
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Error message if failed"
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Number of retries"
    )
    transcription_started_at: Mapped[str | None] = mapped_column(
        DateTime,
        nullable=True,
        doc="When transcription started"
    )
    recognized_at: Mapped[str | None] = mapped_column(
        DateTime,
        nullable=True,
        doc="When transcription completed"
    )

    # Relationships
    episode = relationship("Episode", back_populates="segments")
    transcript_cues = relationship("TranscriptCue", back_populates="segment", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("episode_id", "segment_index", name="_episode_segment_uc"),
        Index("idx_episode_segment", "episode_id", "segment_index"),
        Index("idx_segment_status", "status"),
        Index("idx_episode_status_segment", "episode_id", "status", "segment_index"),
    )

    @property
    def duration(self) -> float:
        """Segment duration in seconds (dynamically calculated)."""
        return self.end_time - self.start_time

    def __repr__(self) -> str:
        return f"<AudioSegment(id={self.id}, segment_id='{self.segment_id}', status='{self.status}')>"
