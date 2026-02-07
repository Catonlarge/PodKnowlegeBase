"""
Translation Service Pydantic Schemas

This module defines Pydantic models for translation service.
These models enforce strict validation on AI-generated translations.
"""
from pydantic import BaseModel, Field, field_validator
from typing import List, Literal


class TranslationItem(BaseModel):
    """
    Single translation item.

    Attributes:
        cue_id: Subtitle cue ID
        original_text: Original text
        translated_text: Translated text
        direction: Translation direction (en_to_zh or zh_to_en)
    """

    cue_id: int = Field(..., ge=1, description="字幕ID")
    original_text: str = Field(..., min_length=1, max_length=500, description="原文")
    translated_text: str = Field(..., min_length=1, max_length=500, description="译文")
    direction: Literal["en_to_zh", "zh_to_en"] = Field(
        ..., description="翻译方向: en_to_zh (英译中) 或 zh_to_en (中译英)"
    )


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
