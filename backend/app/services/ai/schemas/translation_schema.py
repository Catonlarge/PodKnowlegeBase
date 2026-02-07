"""
Translation Service Pydantic Schemas

This module defines Pydantic models for translation service.
These models enforce strict validation on AI-generated translations.
"""
from pydantic import BaseModel, Field, field_validator
from typing import List


class TranslationItem(BaseModel):
    """
    Single translation item.

    Attributes:
        cue_id: Subtitle cue ID
        original_text: Original text (for verification)
        translated_text: Translated text
    """

    cue_id: int = Field(..., ge=1, description="字幕ID")
    original_text: str = Field(..., min_length=1, description="原文")
    translated_text: str = Field(..., min_length=1, description="译文")


class TranslationResponse(BaseModel):
    """
    Root response model for translation service.

    Contains a list of translation items with validation
    to ensure no duplicate cue_ids.
    """

    translations: List[TranslationItem] = Field(default_factory=list)

    @field_validator('translations')
    @classmethod
    def validate_unique_cue_ids(cls, v):
        """
        Validate that all cue_ids are unique.

        Args:
            v: List of TranslationItem

        Raises:
            ValueError: If duplicate cue_ids are found
        """
        cue_ids = [t.cue_id for t in v]
        if len(cue_ids) != len(set(cue_ids)):
            raise ValueError('存在重复的cue_id')
        return v


__all__ = [
    "TranslationItem",
    "TranslationResponse",
]
