"""
Proofreading Service Pydantic Schemas

This module defines Pydantic models for subtitle proofreading service.
These models enforce strict validation on AI-generated correction suggestions.
"""
from pydantic import BaseModel, Field, field_validator
from typing import List


class CorrectionSuggestion(BaseModel):
    """
    Individual correction suggestion from AI proofreading.

    Attributes:
        cue_id: Subtitle cue ID (must be >= 1)
        original_text: Original text from transcription
        corrected_text: Corrected text suggested by AI
        reason: Explanation for the correction
        confidence: Confidence score (0.0 to 1.0)
    """

    cue_id: int = Field(..., description="字幕ID", ge=1)
    original_text: str = Field(..., min_length=1, max_length=500)
    corrected_text: str = Field(..., min_length=1, max_length=500)
    reason: str = Field(..., min_length=1, max_length=200)
    confidence: float = Field(..., ge=0.0, le=1.0)


class ProofreadingResponse(BaseModel):
    """
    Root response model for proofreading service.

    Contains a list of correction suggestions with validation
    to ensure no duplicate cue_ids and at least one correction.
    """

    corrections: List[CorrectionSuggestion] = Field(..., min_length=1)

    @field_validator('corrections')
    @classmethod
    def validate_unique_cue_ids(cls, v):
        """
        Validate that all cue_ids are unique.

        Args:
            v: List of CorrectionSuggestion

        Raises:
            ValueError: If duplicate cue_ids are found
        """
        cue_ids = [c.cue_id for c in v]
        if len(cue_ids) != len(set(cue_ids)):
            raise ValueError('存在重复的cue_id')
        return v


__all__ = [
    "CorrectionSuggestion",
    "ProofreadingResponse",
]
