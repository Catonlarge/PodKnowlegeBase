"""
Translation Schemas

Pydantic models for Translation API request/response validation.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TranslationUpdate(BaseModel):
    """更新翻译请求"""

    translation: str = Field(..., description="修正后的翻译", min_length=1)


class TranslationResponse(BaseModel):
    """翻译响应"""

    id: int
    cue_id: int
    language_code: str
    original_translation: Optional[str]
    translation: Optional[str]
    is_edited: bool
    translation_status: str
    translation_error: Optional[str]
    translation_completed_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class BatchTranslateRequest(BaseModel):
    """批量翻译请求"""

    language_code: str = Field("zh", description="目标语言代码")
    force: bool = Field(False, description="强制重新翻译（跳过断点）")


class BatchTranslateResponse(BaseModel):
    """批量翻译响应"""

    episode_id: int
    language_code: str
    total: int
    completed: int
    skipped: int
    failed: int
