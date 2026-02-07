"""
AI Service Schemas Module

This module exports all Pydantic schemas for AI services.
"""
from .proofreading_schema import CorrectionSuggestion, ProofreadingResponse
from .segmentation_schema import Chapter, SegmentationResponse
from .marketing_schema import MarketingAngle, MultiAngleMarketingResponse
from .translation_schema import TranslationItem, TranslationResponse

__all__ = [
    # Proofreading
    "CorrectionSuggestion",
    "ProofreadingResponse",
    # Segmentation
    "Chapter",
    "SegmentationResponse",
    # Marketing
    "MarketingAngle",
    "MultiAngleMarketingResponse",
    # Translation
    "TranslationItem",
    "TranslationResponse",
]
