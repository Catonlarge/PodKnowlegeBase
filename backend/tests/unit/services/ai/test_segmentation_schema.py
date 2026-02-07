"""
Unit Tests for Segmentation Schema

This module tests the Pydantic schemas for episode segmentation service.
Tests follow BDD naming convention and avoid conditional logic.
"""
import pytest
from pydantic import ValidationError

from app.services.ai.schemas.segmentation_schema import (
    Chapter,
    SegmentationResponse
)


class TestChapter:
    """测试 Chapter 模型"""

    def test_valid_chapter_with_minimal_data_passes_validation(self):
        """
        Given: 包含最小有效数据的 Chapter
        When: 创建模型实例
        Then: 验证通过，字段正确赋值
        """
        chapter = Chapter(
            title="第一章",
            summary="这是第一章的摘要",
            start_time=0.0,
            end_time=60.0
        )

        assert chapter.title == "第一章"
        assert chapter.summary == "这是第一章的摘要"
        assert chapter.start_time == 0.0
        assert chapter.end_time == 60.0

    def test_valid_chapter_with_maximal_data_passes_validation(self):
        """
        Given: 包含最大有效数据的 Chapter
        When: 创建模型实例
        Then: 验证通过
        """
        chapter = Chapter(
            title="a" * 100,
            summary="b" * 1000,
            start_time=0.0,
            end_time=99999.99
        )

        assert len(chapter.title) == 100
        assert len(chapter.summary) == 1000
        assert chapter.end_time == 99999.99

    def test_valid_chapter_with_zero_start_time_passes_validation(self):
        """
        Given: start_time 为 0.0
        When: 创建模型实例
        Then: 验证通过
        """
        chapter = Chapter(
            title="第一章",
            summary="摘要",
            start_time=0.0,
            end_time=60.0
        )

        assert chapter.start_time == 0.0

    def test_chapter_with_negative_start_time_raises_validation_error(self):
        """
        Given: start_time 为负数
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            Chapter(
                title="第一章",
                summary="摘要",
                start_time=-1.0,
                end_time=60.0
            )

    def test_chapter_with_zero_end_time_raises_validation_error(self):
        """
        Given: end_time 为 0.0
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            Chapter(
                title="第一章",
                summary="摘要",
                start_time=0.0,
                end_time=0.0
            )

    def test_chapter_with_negative_end_time_raises_validation_error(self):
        """
        Given: end_time 为负数
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            Chapter(
                title="第一章",
                summary="摘要",
                start_time=0.0,
                end_time=-10.0
            )

    def test_chapter_with_empty_title_raises_validation_error(self):
        """
        Given: title 为空字符串
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            Chapter(
                title="",
                summary="摘要",
                start_time=0.0,
                end_time=60.0
            )

    def test_chapter_with_too_long_title_raises_validation_error(self):
        """
        Given: title 长度大于 100
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            Chapter(
                title="a" * 101,
                summary="摘要",
                start_time=0.0,
                end_time=60.0
            )

    def test_chapter_with_empty_summary_raises_validation_error(self):
        """
        Given: summary 为空字符串
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            Chapter(
                title="第一章",
                summary="",
                start_time=0.0,
                end_time=60.0
            )

    def test_chapter_with_too_long_summary_raises_validation_error(self):
        """
        Given: summary 长度大于 1000
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            Chapter(
                title="第一章",
                summary="a" * 1001,
                start_time=0.0,
                end_time=60.0
            )

    def test_chapter_with_end_time_equal_to_start_time_raises_validation_error(self):
        """
        Given: end_time 等于 start_time
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError, match="end_time.*必须大于 start_time"):
            Chapter(
                title="第一章",
                summary="摘要",
                start_time=60.0,
                end_time=60.0
            )

    def test_chapter_with_end_time_less_than_start_time_raises_validation_error(self):
        """
        Given: end_time 小于 start_time
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError, match="end_time.*必须大于 start_time"):
            Chapter(
                title="第一章",
                summary="摘要",
                start_time=120.0,
                end_time=60.0
            )

    def test_chapter_with_valid_time_range_passes_validation(self):
        """
        Given: 有效的 time_range (end_time > start_time)
        When: 创建模型实例
        Then: 验证通过
        """
        chapter = Chapter(
            title="第一章",
            summary="摘要",
            start_time=100.5,
            end_time=200.8
        )

        assert chapter.start_time == 100.5
        assert chapter.end_time == 200.8


class TestSegmentationResponse:
    """测试 SegmentationResponse 模型"""

    def test_valid_response_with_min_chapters_passes_validation(self):
        """
        Given: 包含最小数量章节（1个）的有效响应
        When: 创建模型实例
        Then: 验证通过
        """
        response = SegmentationResponse(
            chapters=[
                Chapter(
                    title="第一章",
                    summary="摘要",
                    start_time=0.0,
                    end_time=60.0
                )
            ]
        )

        assert len(response.chapters) == 1

    def test_valid_response_with_max_chapters_passes_validation(self):
        """
        Given: 包含最大数量章节（50个）的有效响应
        When: 创建模型实例
        Then: 验证通过
        """
        chapters = []
        for i in range(50):
            chapters.append(Chapter(
                title=f"第{i+1}章",
                summary=f"摘要{i}",
                start_time=float(i * 60),
                end_time=float((i + 1) * 60)
            ))

        response = SegmentationResponse(chapters=chapters)

        assert len(response.chapters) == 50

    def test_response_with_zero_chapters_raises_validation_error(self):
        """
        Given: chapters 为空列表
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError):
            SegmentationResponse(chapters=[])

    def test_response_with_more_than_max_chapters_raises_validation_error(self):
        """
        Given: chapters 数量大于 50
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        chapters = []
        for i in range(51):
            chapters.append(Chapter(
                title=f"第{i+1}章",
                summary=f"摘要{i}",
                start_time=float(i * 60),
                end_time=float((i + 1) * 60)
            ))

        with pytest.raises(ValidationError):
            SegmentationResponse(chapters=chapters)

    def test_response_with_unsorted_chapters_raises_validation_error(self):
        """
        Given: 章节未按 start_time 排序
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValueError, match="必须按 start_time 排序"):
            SegmentationResponse(
                chapters=[
                    Chapter(
                        title="第二章",
                        summary="摘要2",
                        start_time=60.0,
                        end_time=120.0
                    ),
                    Chapter(
                        title="第一章",
                        summary="摘要1",
                        start_time=0.0,
                        end_time=60.0
                    ),
                ]
            )

    def test_response_with_adjacent_chapters_passes_validation(self):
        """
        Given: 相邻章节（end_time == next start_time）
        When: 创建模型实例
        Then: 验证通过
        """
        response = SegmentationResponse(
            chapters=[
                Chapter(
                    title="第一章",
                    summary="摘要1",
                    start_time=0.0,
                    end_time=60.0
                ),
                Chapter(
                    title="第二章",
                    summary="摘要2",
                    start_time=60.0,
                    end_time=120.0
                ),
                Chapter(
                    title="第三章",
                    summary="摘要3",
                    start_time=120.0,
                    end_time=180.0
                ),
            ]
        )

        assert len(response.chapters) == 3

    def test_response_with_overlapping_chapters_raises_validation_error(self):
        """
        Given: 章节时间重叠
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError, match="存在时间重叠"):
            SegmentationResponse(
                chapters=[
                    Chapter(
                        title="第一章",
                        summary="摘要1",
                        start_time=0.0,
                        end_time=90.0
                    ),
                    Chapter(
                        title="第二章",
                        summary="摘要2",
                        start_time=60.0,
                        end_time=120.0
                    ),
                ]
            )

    def test_response_with_chapter_extending_into_next_raises_validation_error(self):
        """
        Given: 第一章的 end_time 大于第二章的 start_time
        When: 创建模型实例
        Then: 抛出 ValidationError
        """
        with pytest.raises(ValidationError, match="存在时间重叠"):
            SegmentationResponse(
                chapters=[
                    Chapter(
                        title="第一章",
                        summary="摘要1",
                        start_time=0.0,
                        end_time=150.0
                    ),
                    Chapter(
                        title="第二章",
                        summary="摘要2",
                        start_time=100.0,
                        end_time=200.0
                    ),
                ]
            )

    def test_response_with_gap_between_chapters_passes_validation(self):
        """
        Given: 章节之间有时间间隔
        When: 创建模型实例
        Then: 验证通过（允许间隔）
        """
        response = SegmentationResponse(
            chapters=[
                Chapter(
                    title="第一章",
                    summary="摘要1",
                    start_time=0.0,
                    end_time=60.0
                ),
                Chapter(
                    title="第二章",
                    summary="摘要2",
                    start_time=90.0,
                    end_time=150.0
                ),
            ]
        )

        assert len(response.chapters) == 2
        assert response.chapters[0].end_time == 60.0
        assert response.chapters[1].start_time == 90.0

    def test_response_json_serialization_deserialization(self):
        """
        Given: 有效的 SegmentationResponse
        When: 序列化为 JSON 再反序列化
        Then: 数据保持一致
        """
        original = SegmentationResponse(
            chapters=[
                Chapter(
                    title="开场介绍",
                    summary="主持人介绍了今天的主题",
                    start_time=0.0,
                    end_time=120.5
                ),
                Chapter(
                    title="核心内容",
                    summary="深入讲解了关键技术",
                    start_time=120.5,
                    end_time=600.0
                ),
            ]
        )

        # 序列化
        json_str = original.model_dump_json()

        # 反序列化
        restored = SegmentationResponse.model_validate_json(json_str)

        assert len(restored.chapters) == 2
        assert restored.chapters[0].title == "开场介绍"
        assert restored.chapters[1].title == "核心内容"
        assert restored.chapters[0].start_time == 0.0
        assert restored.chapters[1].end_time == 600.0
