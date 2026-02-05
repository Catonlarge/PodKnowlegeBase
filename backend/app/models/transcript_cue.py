"""
TranscriptCue Model

Represents a single subtitle cue (English text) with timing.
"""
from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, Index
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
        text: Original English subtitle text from Whisper
        corrected_text: LLM-corrected text (if any)
        is_corrected: Whether the cue has been corrected
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
        doc="Original English subtitle text from Whisper"
    )
    corrected_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="LLM-corrected text (if proofreading has been applied)"
    )
    is_corrected: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc="Whether this cue has been corrected by LLM"
    )

    # Relationships
    segment = relationship("AudioSegment", back_populates="transcript_cues")
    chapter = relationship("Chapter", back_populates="transcript_cues")
    translations = relationship("Translation", back_populates="cue", cascade="all, delete-orphan")
    transcript_corrections = relationship(
        "TranscriptCorrection",
        back_populates="cue",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_segment_id", "segment_id"),
        Index("idx_cue_chapter", "chapter_id"),
        Index("idx_cue_start_time", "segment_id", "start_time"),
        Index("idx_cue_is_corrected", "is_corrected"),
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

    @property
    def effective_text(self) -> str:
        """
        Get the effective text to use.

        Returns corrected_text if is_corrected=True, otherwise returns original text.

        Returns:
            str: The effective text (corrected or original)
        """
        return self.corrected_text if self.is_corrected else self.text

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

    @property
    def obsidian_anchor(self) -> str:
        """
        Generate Obsidian invisible anchor for linking.

        Creates a markdown link with time display and cue://ID reference.
        Format: [MM:SS](cue://ID) or [HH:MM:SS](cue://ID) for content >= 1 hour

        Returns:
            str: Obsidian markdown anchor link

        Examples:
            start_time=65.5, id=1 -> "[01:05](cue://1)"
            start_time=3665.0, id=2 -> "[01:01:05](cue://2)"
        """
        total_seconds = int(self.start_time)
        minutes = total_seconds // 60
        seconds = total_seconds % 60

        if minutes >= 60:
            hours = minutes // 60
            minutes = minutes % 60
            time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            time_str = f"{minutes:02d}:{seconds:02d}"

        return f"[{time_str}](cue://{self.id})"

    def __repr__(self) -> str:
        # Create a preview of the effective text (first 20 chars)
        text_preview = self.effective_text[:20] + "..." if len(self.effective_text) > 20 else self.effective_text
        return f"<TranscriptCue(id={self.id}, text='{text_preview}')>"
