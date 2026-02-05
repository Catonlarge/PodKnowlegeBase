"""
MarketingPost Model

Supports content racing with 1:N stacking multi-angle distribution.
"""
from sqlalchemy import Float, ForeignKey, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class MarketingPost(Base, TimestampMixin):
    """
    Represents a marketing post with content racing strategy.

    This model supports the "Content Racing" design:
    - No unique constraint (allows multiple posts per episode with different angles)
    - angle_tag field for strategy labels (e.g., "职场焦虑向", "干货硬核向")
    - chapter_id can be NULL (full-episode posts) or has value (chapter-specific posts)

    Attributes:
        id: Primary key
        episode_id: Foreign key to Episode
        chapter_id: Foreign key to Chapter (nullable, for chapter-specific posts)
        platform: Platform identifier ('xhs', 'twitter', 'bilibili', etc.)
        angle_tag: Strategy label for content categorization
        title: Post title/first image caption
        content: Full marketing content with emoji and formatting
        status: Post status
    """

    __tablename__ = "marketing_posts"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign keys
    episode_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("episodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Foreign key to Episode"
    )
    chapter_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("chapters.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Foreign key to Chapter (NULL for full-episode, has value for chapter-specific)"
    )

    # Platform and strategy
    platform: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        doc="Platform identifier ('xhs', 'twitter', 'bilibili', etc.)"
    )
    angle_tag: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        doc="Strategy label (e.g., '职场焦虑向', '干货硬核向')"
    )

    # Content
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Post title/first image caption"
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Full marketing content with emoji and formatting"
    )

    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        doc="Post status"
    )

    # Relationships
    episode = relationship("Episode", back_populates="marketing_posts")
    chapter = relationship("Chapter")

    # Note: No unique constraint - this is intentional for Content Racing design
    # Multiple posts can exist for the same episode with different angles
    __table_args__ = (
        Index("idx_marketing_episode", "episode_id"),
        Index("idx_marketing_chapter", "chapter_id"),
        Index("idx_marketing_platform", "platform"),
        Index("idx_marketing_angle", "angle_tag"),
        Index("idx_marketing_ep_angle", "episode_id", "angle_tag"),
    )

    def __repr__(self) -> str:
        return f"<MarketingPost(id={self.id}, platform='{self.platform}', angle_tag='{self.angle_tag}')>"
