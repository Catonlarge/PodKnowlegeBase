"""
Publication Schemas

Pydantic models for PublicationRecord API request/response validation.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class PublicationRecordResponse(BaseModel):
    """发布记录响应"""

    id: int
    episode_id: int
    platform: str
    platform_record_id: Optional[str]
    status: str
    published_at: Optional[datetime]
    error_message: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class PublicationStatusResponse(BaseModel):
    """发布状态响应"""

    episode_id: int
    records: list[PublicationRecordResponse]
    summary: dict


class RetryPublicationResponse(BaseModel):
    """重试发布响应"""

    id: int
    status: str
    message: Optional[str] = None
