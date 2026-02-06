"""
Transcript Schemas

Pydantic models for TranscriptCue API request/response validation.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TranscriptCueResponse(BaseModel):
    """字幕响应"""

    id: int
    segment_id: Optional[int]
    start_time: float
    end_time: float
    speaker: str
    text: str
    corrected_text: Optional[str]
    is_corrected: bool
    chapter_id: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}


class TranscriptCueWithTranslationResponse(TranscriptCueResponse):
    """带翻译的字幕响应"""

    translation: Optional[str] = None


class TranscriptListResponse(BaseModel):
    """字幕列表响应"""

    episode_id: int
    total: int
    items: list[TranscriptCueWithTranslationResponse]


class EffectiveTextResponse(BaseModel):
    """有效文本响应"""

    cue_id: int
    text: str
    is_corrected: bool
