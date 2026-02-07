"""
Segmentation Service Business Validator

This module provides business logic validation for segmentation/chapter service.
It validates Pydantic-validated responses against business rules.
"""
from loguru import logger

from app.services.ai.schemas.segmentation_schema import SegmentationResponse


class SegmentationValidator:
    """
    Business logic validator for segmentation service.

    Validates:
    - First chapter starts at 0
    - Chapters don't overlap (also in Pydantic, but double-check)
    - Last chapter doesn't exceed total duration
    - Chapter count is reasonable
    """

    @staticmethod
    def validate(
        response: SegmentationResponse,
        total_duration: float,
        min_chapter_duration: float = 30.0,
        max_chapter_count: int = 20
    ) -> SegmentationResponse:
        """
        Validate segmentation response against business rules.

        Args:
            response: Validated Pydantic response
            total_duration: Total duration of the episode in seconds
            min_chapter_duration: Minimum duration for a chapter (default: 30s)
            max_chapter_count: Maximum reasonable chapter count (default: 20)

        Returns:
            The validated response (unchanged if validation passes)

        Raises:
            ValueError: If business validation fails

        Examples:
            >>> validator = SegmentationValidator()
            >>> result = validator.validate(response, total_duration=180.0)
        """
        chapters = response.chapters

        # Validation 1: At least one chapter
        if not chapters:
            raise ValueError("章节分析结果不能为空")

        # Validation 2: First chapter starts at 0
        if chapters[0].start_time != 0:
            raise ValueError(
                f"第一章必须从0秒开始，实际: {chapters[0].start_time}秒"
            )

        # Validation 3: Chapters don't overlap (double-check Pydantic validation)
        for i in range(len(chapters) - 1):
            if chapters[i].end_time > chapters[i + 1].start_time:
                raise ValueError(
                    f"章节 {i + 1} 和 {i + 2} 存在时间重叠: "
                    f"章节 {i + 1} 结束于 {chapters[i].end_time}秒, "
                    f"章节 {i + 2} 开始于 {chapters[i + 1].start_time}秒"
                )

        # Validation 4: Last chapter doesn't exceed total duration
        last_end = chapters[-1].end_time
        max_allowed = total_duration * 1.1  # Allow 10% tolerance

        if last_end > max_allowed:
            raise ValueError(
                f"最后章节结束时间({last_end:.1f}秒) "
                f"超出总时长({total_duration:.1f}秒, 允许上限{max_allowed:.1f}秒)"
            )

        # Validation 5: Minimum chapter duration
        for i, chapter in enumerate(chapters):
            duration = chapter.end_time - chapter.start_time
            if duration < min_chapter_duration:
                logger.warning(
                    f"章节 {i + 1} 时长过短: {duration:.1f}秒 (最小建议: {min_chapter_duration}秒)"
                )

        # Validation 6: Chapter count is reasonable
        chapter_count = len(chapters)
        if chapter_count > max_chapter_count:
            logger.warning(
                f"章节数量过多: {chapter_count} (建议最大: {max_chapter_count})"
            )

        return response


__all__ = [
    "SegmentationValidator",
]
