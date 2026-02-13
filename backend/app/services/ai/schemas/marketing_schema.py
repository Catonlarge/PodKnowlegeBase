"""
Marketing Service Pydantic Schemas

This module defines Pydantic models for marketing content generation service.
These models enforce strict validation on AI-generated marketing copy.
"""
import re
from pydantic import BaseModel, Field, field_validator
from typing import List


# 匹配 # 开头的标签（字母数字下划线 + 中文）
_HASHTAG_PATTERN = re.compile(r'#[\w\u4e00-\u9fff]+')


def _expand_hashtags_list(v: List) -> List[str]:
    """
    Expand hashtags when LLM returns ["#a #b #c"] or ["#a#b#c"] as single string.

    Strategy:
    1. Split by separators: space, comma, Chinese comma(，) semicolon(；) enum(、)
    2. For each part with multiple # (e.g. "#a#b"), use regex findall to extract tags

    Returns flat list of individual strings (each may or may not start with #).
    """
    result: List[str] = []
    for item in v:
        if not isinstance(item, str):
            continue
        s = item.strip()
        if not s:
            continue
        parts = re.split(r'[\s,，；、]+', s)
        for p in parts:
            p = p.strip()
            if not p:
                continue
            if p.count('#') >= 2:
                result.extend(_HASHTAG_PATTERN.findall(p))
            else:
                result.append(p)
    return result


class MarketingAngle(BaseModel):
    """
    Single marketing angle with generated content.

    Attributes:
        angle_name: Name/identifier of the marketing angle
        title: Content title
        content: Main content body (200-800 characters)
        hashtags: List of hashtags (3-10 tags, each starting with #)
    """

    angle_name: str = Field(..., min_length=2, max_length=20, description="营销角度名称")
    title: str = Field(..., min_length=5, max_length=60, description="标题（建议30字以内，允许最多60字）")
    content: str = Field(..., min_length=200, max_length=800, description="正文内容")
    hashtags: List[str] = Field(..., min_length=3, max_length=10, description="标签列表")

    @field_validator('content', mode='before')
    @classmethod
    def truncate_content(cls, v):
        """Truncate content to 800 chars when LLM returns longer (avoids schema rejection)."""
        if isinstance(v, str) and len(v) > 800:
            return v[:797] + '...'
        return v

    @field_validator('hashtags', mode='before')
    @classmethod
    def normalize_and_validate_hashtags(cls, v):
        """
        Normalize and validate hashtags. LLM may return ["#a #b #c"] as single string.
        """
        if not v:
            return v
        expanded = _expand_hashtags_list(v if isinstance(v, list) else [v])
        validated: List[str] = []
        for tag in expanded:
            tag_clean = tag.strip()
            if not tag_clean.startswith('#'):
                raise ValueError(f'标签必须以#开头: {tag_clean}')
            if len(tag_clean) > 20:
                raise ValueError(f'标签过长(最多20字符): {tag_clean}')
            validated.append(tag_clean)
        if len(validated) < 3:
            raise ValueError(f'至少需要3个独立标签，当前: {validated}')
        return validated[:10]


class MultiAngleMarketingResponse(BaseModel):
    """
    Root response model for multi-angle marketing generation.

    Contains exactly 3 marketing angles with unique angle names.
    """

    angles: List[MarketingAngle] = Field(..., min_length=3, max_length=3)

    @field_validator('angles')
    @classmethod
    def validate_unique_angles(cls, v):
        """
        Validate that all angle names are unique.

        Args:
            v: List of MarketingAngle

        Raises:
            ValueError: If angle names are not unique
        """
        angle_names = [a.angle_name for a in v]
        if len(angle_names) != len(set(angle_names)):
            raise ValueError('角度名称必须唯一')
        return v


__all__ = [
    "MarketingAngle",
    "MultiAngleMarketingResponse",
]
