"""
PublicationRecord Model

Tracks publication records across platforms.
"""
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class PublicationRecord(Base, TimestampMixin):
    """
    Represents a publication record for tracking platform distribution.

    This model stores publication history including retry attempts.
    No unique constraint on (episode_id, platform) allows for retry tracking.

    Attributes:
        id: Primary key
        episode_id: Foreign key to Episode
        platform: Platform name ('feishu', 'ima', 'marketing')
        platform_record_id: Platform's record ID (nullable)
        status: Publication status
        published_at: When publication completed
        error_message: Error message if failed
    """

    __tablename__ = "publication_records"

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

    # Platform information
    platform: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        doc="Platform name ('feishu', 'ima', 'marketing')"
    )
    platform_record_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        doc="Platform's record ID"
    )

    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
        doc="Publication status"
    )
    published_at: Mapped[str | None] = mapped_column(
        DateTime,
        nullable=True,
        doc="When publication completed"
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Error message if failed"
    )

    # Relationships
    episode = relationship("Episode", back_populates="publication_records")

    # Note: No unique constraint on (episode_id, platform) to allow retry history
    __table_args__ = (
        Index("idx_pub_episode", "episode_id"),
        Index("idx_pub_platform", "platform"),
        Index("idx_pub_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<PublicationRecord(id={self.id}, platform='{self.platform}', status='{self.status}')>"
