"""
Segmentation Service Pydantic Schemas

This module defines Pydantic models for episode segmentation/chapter analysis service.
These models enforce strict validation on AI-generated chapter divisions.
"""
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List


class Chapter(BaseModel):
    """
    Single chapter/segment of an episode.

    Attributes:
        title: Chapter title
        summary: Chapter summary
        start_time: Start time in seconds
        end_time: End time in seconds
    """

    title: str = Field(..., min_length=1, max_length=100)
    summary: str = Field(..., min_length=1, max_length=1000)
    start_time: float = Field(..., ge=0.0, description="开始时间（秒）")
    end_time: float = Field(..., gt=0.0, description="结束时间（秒）")

    @model_validator(mode='after')
    def validate_time_range(self):
        """
        Validate that end_time > start_time.

        Raises:
            ValueError: If end_time is not greater than start_time
        """
        if self.end_time <= self.start_time:
            raise ValueError(f'end_time ({self.end_time}) 必须大于 start_time ({self.start_time})')
        return self


class SegmentationResponse(BaseModel):
    """
    Root response model for segmentation service.

    Contains a list of chapters with validation for:
    - At least 1 chapter, at most 50 chapters
    - No overlapping chapters
    """

    chapters: List[Chapter] = Field(..., min_length=1, max_length=50)

    @field_validator('chapters')
    @classmethod
    def validate_no_overlap(cls, v):
        """
        Validate that chapters don't overlap in time.

        Args:
            v: List of Chapter

        Raises:
            ValueError: If chapters overlap
        """
        for i in range(len(v) - 1):
            if v[i].end_time > v[i + 1].start_time:
                raise ValueError(
                    f'章节 {i + 1} 和 {i + 2} 存在时间重叠: '
                    f'章节 {i + 1} 结束于 {v[i].end_time}秒, '
                    f'章节 {i + 2} 开始于 {v[i + 1].start_time}秒'
                )
        return v


__all__ = [
    "Chapter",
    "SegmentationResponse",
]
