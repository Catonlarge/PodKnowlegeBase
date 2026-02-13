"""
Marketing Service Pydantic Schemas

This module defines Pydantic models for marketing content generation service.
These models enforce strict validation on AI-generated marketing copy.
"""
from pydantic import BaseModel, Field, field_validator
from typing import List


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

    @field_validator('hashtags')
    @classmethod
    def validate_hashtags_format(cls, v):
        """
        Validate that all hashtags start with # and are not too long.

        Args:
            v: List of hashtag strings

        Raises:
            ValueError: If hashtag format is invalid
        """
        for tag in v:
            # Strip whitespace before checking
            tag_clean = tag.strip()
            if not tag_clean.startswith('#'):
                raise ValueError(f'标签必须以#开头: {tag}')
            if len(tag_clean) > 20:
                raise ValueError(f'标签过长(最多20字符): {tag}')
        return v


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
