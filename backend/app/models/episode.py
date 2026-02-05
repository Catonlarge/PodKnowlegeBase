"""
Episode Model

Represents a podcast episode with metadata and workflow status.
"""
from sqlalchemy import Float, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.enums.workflow_status import WorkflowStatus


class Episode(Base, TimestampMixin):
    """
    Represents a podcast episode.

    Attributes:
        id: Primary key
        title: Episode title
        show_name: Podcast show name (from metadata)
        source_url: Original URL (YouTube/Bilibili/etc.)
        audio_path: Local audio file path
        file_hash: MD5 hash for deduplication (unique)
        file_size: File size in bytes
        duration: Duration in seconds
        language: Language code (default: 'en-US')
        ai_summary: AI-generated full summary
        workflow_status: Workflow status (0-6)

    Note: Relationships to other models will be added after those models are created.
    """

    __tablename__ = "episodes"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Basic metadata
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    show_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    audio_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # File information
    file_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        doc="MD5 hash for deduplication"
    )
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True, doc="File size in bytes")

    # Audio information
    duration: Mapped[float] = mapped_column(Float, nullable=False, doc="Duration in seconds")
    language: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="en-US",
        doc="Language code"
    )

    # AI-generated content
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True, doc="AI-generated summary")

    # Workflow status
    workflow_status: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=WorkflowStatus.INIT.value,
        index=True,
        doc="Workflow status (0-6)"
    )

    # Relationships
    segments = relationship("AudioSegment", back_populates="episode", cascade="all, delete-orphan")
    # transcript_cues = relationship("TranscriptCue", back_populates="episode", cascade="all, delete-orphan")
    chapters = relationship("Chapter", back_populates="episode", cascade="all, delete-orphan")
    publication_records = relationship("PublicationRecord", back_populates="episode", cascade="all, delete-orphan")
    marketing_posts = relationship("MarketingPost", back_populates="episode", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_episodes_file_hash", "file_hash", unique=True),
        Index("idx_episodes_workflow_status", "workflow_status"),
    )

    def __repr__(self) -> str:
        return f"<Episode(id={self.id}, title='{self.title}', status={self.workflow_status})>"
