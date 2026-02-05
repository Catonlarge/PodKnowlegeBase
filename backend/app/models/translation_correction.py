"""
TranslationCorrection Model

Stores AI translation corrections for Token optimization (Patch Mode).
"""
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class TranslationCorrection(Base, TimestampMixin):
    """
    Represents an AI translation correction for Token optimization.

    This model stores corrections made to AI translations, serving as
    training data for improving future translations (Patch Mode).

    Attributes:
        id: Primary key
        cue_id: Foreign key to TranscriptCue
        language_code: Language code of the correction
        original_text: Original AI translation
        corrected_text: Corrected translation
        ai_model: AI model used for correction
    """

    __tablename__ = "translation_corrections"

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
        doc="Language code of the correction"
    )

    # Content
    original_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Original AI translation"
    )
    corrected_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Corrected translation"
    )

    # Metadata
    ai_model: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        doc="AI model used for correction"
    )

    # Relationships
    cue = relationship("TranscriptCue")

    __table_args__ = (
        Index("idx_corr_cue", "cue_id"),
        Index("idx_corr_language", "language_code"),
    )

    def __repr__(self) -> str:
        return f"<TranslationCorrection(id={self.id}, language_code='{self.language_code}')>"
