"""
Translation Model

Stores RLHF dual-text translations for transcript cues.
"""
from sqlalchemy import Boolean, DateTime, event, ForeignKey, Integer, String, Text, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.enums.translation_status import TranslationStatus


class Translation(Base, TimestampMixin):
    """
    Represents a translation with RLHF (Reinforcement Learning from Human Feedback) dual-text design.

    This model supports:
    - Storing AI original version (immutable after first generation)
    - Storing current active version (user-editable)
    - RLHF flag (is_edited) for training data export

    Attributes:
        id: Primary key
        cue_id: Foreign key to TranscriptCue
        language_code: Language code ('zh', 'ja', 'fr', etc.)
        original_translation: AI original version (immutable after first set)
        translation: Current active version (user-editable)
        is_edited: RLHF flag (True when original != current)
        translation_status: Translation status
        translation_error: Error message if failed
        translation_retry_count: Number of retries
        translation_started_at: When translation started
        translation_completed_at: When translation completed

    RLHF Workflow:
        1. LLM generates translation -> both original and translation set to same value
        2. User edits in Obsidian -> only translation field updated
        3. is_edited flag indicates data available for RLHF training
    """

    __tablename__ = "translations"

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

    # Language identification
    language_code: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        index=True,
        doc="Language code ('zh', 'ja', 'fr', etc.)"
    )

    # RLHF dual-text fields
    original_translation: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="AI original version (immutable after first set)"
    )
    translation: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Current active version (user-editable)"
    )
    is_edited: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
        doc="RLHF flag: True when original != current"
    )

    # Translation status fields
    translation_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=TranslationStatus.PENDING.value,
        index=True,
        doc="Translation status"
    )
    translation_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Translation error message"
    )
    translation_retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Number of translation retries"
    )
    translation_started_at: Mapped[str | None] = mapped_column(
        DateTime,
        nullable=True,
        doc="When translation started"
    )
    translation_completed_at: Mapped[str | None] = mapped_column(
        DateTime,
        nullable=True,
        doc="When translation completed"
    )

    # Relationships
    cue = relationship("TranscriptCue", back_populates="translations")

    __table_args__ = (
        UniqueConstraint("cue_id", "language_code", name="_cue_language_uc"),
        Index("idx_translations_cue", "cue_id"),
        Index("idx_translations_language", "language_code"),
        Index("idx_translation_status", "translation_status"),
        Index("idx_translation_ep_lang_status", "cue_id", "language_code", "translation_status"),
        Index("idx_translation_is_edited", "is_edited"),
    )

    def __repr__(self) -> str:
        return f"<Translation(id={self.id}, language_code='{self.language_code}', status='{self.translation_status}')>"


# Event listener to automatically set original_translation from translation on first insert
@event.listens_for(Translation, "before_insert")
def auto_set_original_translation(mapper, connection, target: Translation):
    """
    Automatically set original_translation from translation when not set.

    This implements the RLHF dual-text design where:
    1. On first creation, both original_translation and translation are set to the same value
    2. Later updates only modify translation (original remains immutable)
    3. The is_edited flag can be used to track which records have been modified
    """
    if target.translation is not None and target.original_translation is None:
        target.original_translation = target.translation
