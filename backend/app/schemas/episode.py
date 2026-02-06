"""
Episode Schemas

Pydantic models for Episode API request/response validation.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class EpisodeCreate(BaseModel):
    """创建 Episode 请求"""

    url: str = Field(..., description="YouTube/Bilibili URL", min_length=1)
    title: Optional[str] = Field(None, description="标题（可选，从元数据自动获取）")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """验证 URL 格式"""
        if not v or not v.strip():
            raise ValueError("URL 不能为空")
        return v.strip()


class EpisodeUpdate(BaseModel):
    """更新 Episode 请求"""

    title: Optional[str] = Field(None, description="标题")
    ai_summary: Optional[str] = Field(None, description="AI 生成的摘要")


class EpisodeResponse(BaseModel):
    """Episode 响应"""

    id: int
    title: str
    show_name: Optional[str]
    source_url: Optional[str]
    duration: float
    language: str
    workflow_status: int
    proofread_status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EpisodeDetailResponse(EpisodeResponse):
    """Episode 详情响应"""

    audio_path: Optional[str]
    file_hash: str
    file_size: Optional[int]
    ai_summary: Optional[str]
    proofread_at: Optional[datetime]
    # 关联数据统计
    segments_count: int = 0
    cues_count: int = 0
    chapters_count: int = 0
    marketing_posts_count: int = 0


class EpisodeListResponse(BaseModel):
    """Episode 列表响应"""

    total: int
    page: int
    limit: int
    pages: int = 0
    items: list[EpisodeResponse]


class EpisodeWorkflowRequest(BaseModel):
    """触发工作流请求"""

    force_restart: bool = Field(False, description="强制重新开始（忽略断点）")


class EpisodePublishRequest(BaseModel):
    """发布 Episode 请求"""

    generate_marketing: bool = Field(True, description="是否生成营销文案")
    platforms: Optional[list[str]] = Field(
        None, description="指定发布平台（null 表示全部）"
    )


class EpisodeTaskResponse(BaseModel):
    """Episode 后台任务响应"""

    id: int
    message: str
