"""
Chapter Model

Represents AI-generated semantic chapter divisions for podcast episodes.
"""
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Chapter(Base, TimestampMixin):
    """
    Represents an AI-generated semantic chapter division.

    This model stores chapter boundaries and metadata created by AI analysis
    of the podcast content.

    Attributes:
        id: Primary key
        episode_id: Foreign key to Episode
        chapter_index: Chapter sequence number (0, 1, 2...)
        title: Chinese chapter title
        summary: Chinese chapter summary (nullable)
        start_time: Chapter start time (seconds)
        end_time: Chapter end time (seconds)
        status: Chapter processing status
        ai_model_used: AI model used for generation
        processed_at: When processing completed
    """

    __tablename__ = "chapters"

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

    # Chapter identification
    chapter_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Chapter sequence number (0, 1, 2...)"
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Chinese chapter title"
    )

    # Content
    summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Chinese chapter summary"
    )

    # Time range
    start_time: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        doc="Chapter start time (seconds)"
    )
    end_time: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        doc="Chapter end time (seconds)"
    )

    # Processing status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
        doc="Chapter processing status"
    )
    ai_model_used: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        doc="AI model used for generation"
    )
    processed_at: Mapped[str | None] = mapped_column(
        DateTime,
        nullable=True,
        doc="When processing completed"
    )

    # Relationships
    episode = relationship("Episode", back_populates="chapters")
    transcript_cues = relationship("TranscriptCue", back_populates="chapter")

    __table_args__ = (
        UniqueConstraint("episode_id", "chapter_index", name="_episode_chapter_uc"),
        Index("idx_episode_chapter", "episode_id", "chapter_index"),
        Index("idx_chapter_status", "status"),
    )

    @property
    def duration(self) -> float:
        """Chapter duration in seconds (dynamically calculated)."""
        return self.end_time - self.start_time

    def __repr__(self) -> str:
        return f"<Chapter(id={self.id}, title='{self.title}', status='{self.status}')>"
