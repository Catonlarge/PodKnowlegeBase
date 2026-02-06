"""
API Schemas Package

Pydantic models for API request/response validation.
"""

# Episode Schemas
from app.schemas.episode import (
    EpisodeCreate,
    EpisodeUpdate,
    EpisodeResponse,
    EpisodeDetailResponse,
    EpisodeListResponse,
    EpisodeWorkflowRequest,
    EpisodePublishRequest,
)

# Transcript Schemas
from app.schemas.transcript import (
    TranscriptCueResponse,
    TranscriptCueWithTranslationResponse,
    TranscriptListResponse,
    EffectiveTextResponse,
)

# Translation Schemas
from app.schemas.translation import (
    TranslationUpdate,
    TranslationResponse,
    BatchTranslateRequest,
    BatchTranslateResponse,
)

# Chapter Schemas
from app.schemas.chapter import (
    ChapterResponse,
    ChapterDetailResponse,
    ChapterListResponse,
)

# Marketing Schemas
from app.schemas.marketing import (
    MarketingPostResponse,
    GenerateMarketingRequest,
    MarketingPostListResponse,
)

# Publication Schemas
from app.schemas.publication import (
    PublicationRecordResponse,
    PublicationStatusResponse,
    RetryPublicationResponse,
)

__all__ = [
    # Episode
    "EpisodeCreate",
    "EpisodeUpdate",
    "EpisodeResponse",
    "EpisodeDetailResponse",
    "EpisodeListResponse",
    "EpisodeWorkflowRequest",
    "EpisodePublishRequest",
    # Transcript
    "TranscriptCueResponse",
    "TranscriptCueWithTranslationResponse",
    "TranscriptListResponse",
    "EffectiveTextResponse",
    # Translation
    "TranslationUpdate",
    "TranslationResponse",
    "BatchTranslateRequest",
    "BatchTranslateResponse",
    # Chapter
    "ChapterResponse",
    "ChapterDetailResponse",
    "ChapterListResponse",
    # Marketing
    "MarketingPostResponse",
    "GenerateMarketingRequest",
    "MarketingPostListResponse",
    # Publication
    "PublicationRecordResponse",
    "PublicationStatusResponse",
    "RetryPublicationResponse",
]
