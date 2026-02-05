"""
TranscriptCue Model

Represents a single subtitle cue (English text) with timing.
"""
from sqlalchemy import Float, ForeignKey, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class TranscriptCue(Base, TimestampMixin):
    """
    Represents a single subtitle cue (English text).

    This model stores individual subtitle entries with absolute timing
    from the original audio (not relative to segment).

    Attributes:
        id: Primary key
        segment_id: Foreign key to AudioSegment (nullable)
        chapter_id: Foreign key to Chapter (nullable)
        start_time: Absolute time from original audio (seconds)
        end_time: Absolute time from original audio (seconds)
        speaker: Speaker identifier
        text: English subtitle text
    """

    __tablename__ = "transcript_cues"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign keys
    segment_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("audio_segments.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        doc="Foreign key to AudioSegment"
    )
    chapter_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("chapters.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Foreign key to Chapter"
    )

    # Timing (absolute time from original audio)
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

    # Content
    speaker: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="Unknown",
        doc="Speaker identifier"
    )
    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="English subtitle text"
    )

    # Relationships
    segment = relationship("AudioSegment", back_populates="transcript_cues")
    chapter = relationship("Chapter", back_populates="transcript_cues")
    translations = relationship("Translation", back_populates="cue", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_segment_id", "segment_id"),
        Index("idx_cue_chapter", "chapter_id"),
        Index("idx_cue_start_time", "segment_id", "start_time"),
    )

    @property
    def duration(self) -> float:
        """Cue duration in seconds (dynamically calculated)."""
        return self.end_time - self.start_time

    @property
    def episode_id(self) -> int | None:
        """Get episode_id through segment (follows 3NF)."""
        return self.segment.episode_id if self.segment else None

    @property
    def episode(self) -> "Episode | None":
        """Get episode object through segment."""
        return self.segment.episode if self.segment else None

    def get_translation(self, language_code: str = "zh") -> str | None:
        """
        Get translation for specified language.

        Args:
            language_code: Language code (default: "zh")

        Returns:
            Translation text if available and completed, None otherwise
        """
        for t in self.translations:
            if t.language_code == language_code and t.translation_status == "completed":
                return t.translation
        return None

    def __repr__(self) -> str:
        # Create a preview of the text (first 20 chars)
        text_preview = self.text[:20] + "..." if len(self.text) > 20 else self.text
        return f"<TranscriptCue(id={self.id}, text='{text_preview}')>"
