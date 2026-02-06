"""
Marketing Schemas

Pydantic models for MarketingPost API request/response validation.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class MarketingPostResponse(BaseModel):
    """营销文案响应"""

    id: int
    episode_id: int
    chapter_id: Optional[int]
    platform: str
    angle_tag: str
    title: str
    content: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class GenerateMarketingRequest(BaseModel):
    """生成营销文案请求"""

    platform: str = Field("xhs", description="目标平台")
    angles: Optional[list[str]] = Field(None, description="指定内容角度（null 表示全部）")


class MarketingPostListResponse(BaseModel):
    """营销文案列表响应"""

    episode_id: int
    total: int
    items: list[MarketingPostResponse]
