"""
Chapter Schemas

Pydantic models for Chapter API request/response validation.
"""
from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel


class ChapterResponse(BaseModel):
    """章节响应"""

    id: int
    episode_id: int
    chapter_index: int
    title: str
    summary: Optional[str]
    start_time: float
    end_time: float
    status: str
    ai_model_used: Optional[str]
    processed_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class ChapterDetailResponse(ChapterResponse):
    """章节详情响应"""

    duration: float
    cues_count: int = 0


class ChapterListResponse(BaseModel):
    """章节列表响应"""

    episode_id: int
    total: int
    items: list[ChapterResponse]


class ChapterCuesListResponse(BaseModel):
    """章节字幕列表响应"""

    chapter_id: int
    total: int
    items: list[Any]
