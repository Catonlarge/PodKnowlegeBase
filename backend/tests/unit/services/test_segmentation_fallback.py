"""
SegmentationService 兜底功能测试

测试 AI 失败时的单章节兜底策略。
"""
from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from app.services.segmentation_service import SegmentationService
from app.models import Episode, Chapter, TranscriptCue, AudioSegment
from app.enums.workflow_status import WorkflowStatus
from app.services.ai.schemas.segmentation_schema import Chapter as SchemaChapter


class TestSegmentationFallback:
    """测试 SegmentationService 兜底功能"""

    def test_fallback_uses_episode_title(self, test_session):
        """Given: AI失败 When: 使用兜底方案 Then: 章节标题使用 episode.title"""
        # Arrange
        episode = Episode(
            title="测试标题",
            audio_path="/test/path.mp3",
            file_hash="test_hash",
            duration=300.0,
            workflow_status=WorkflowStatus.TRANSCRIBED.value
        )
        test_session.add(episode)
        test_session.flush()

        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=0,
            segment_id="segment_001",
            start_time=0.0,
            end_time=300.0,
            status="completed"
        )
        test_session.add(segment)
        test_session.flush()

        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=0.0,
            end_time=5.0,
            speaker="Speaker",
            text="Hello world"
        )
        test_session.add(cue)
        test_session.flush()

        service = SegmentationService(
            test_session,
            provider="moonshot",
            api_key="test_key"
        )

        # Mock _call_ai_for_segmentation to raise exception
        with patch.object(
            service,
            '_call_ai_for_segmentation',
            side_effect=Exception("AI 调用失败")
        ):
            # Act
            chapters = service.analyze_and_segment(episode.id)

        # Assert
        assert len(chapters) == 1
        assert chapters[0].title == "测试标题"
        assert "AI 章节切分失败" in chapters[0].summary
        assert chapters[0].start_time == 0.0
        assert chapters[0].end_time == 300.0

    def test_fallback_summary_contains_duration(self, test_session):
        """Given: AI失败 When: 使用兜底方案 Then: 摘要包含总时长"""
        # Arrange
        episode = Episode(
            title="测试",
            audio_path="/test/path.mp3",
            file_hash="test_hash",
            duration=600.0,  # 10分钟
            workflow_status=WorkflowStatus.TRANSCRIBED.value
        )
        test_session.add(episode)
        test_session.flush()

        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=0,
            segment_id="segment_001",
            start_time=0.0,
            end_time=600.0,
            status="completed"
        )
        test_session.add(segment)
        test_session.flush()

        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=0.0,
            end_time=5.0,
            speaker="Speaker",
            text="Hello"
        )
        test_session.add(cue)
        test_session.flush()

        service = SegmentationService(
            test_session,
            provider="moonshot",
            api_key="test_key"
        )

        with patch.object(
            service,
            '_call_ai_for_segmentation',
            side_effect=Exception("AI 失败")
        ):
            # Act
            chapters = service.analyze_and_segment(episode.id)

        # Assert
        assert "10.0 分钟" in chapters[0].summary

    def test_fallback_covers_full_duration(self, test_session):
        """Given: AI失败 When: 使用兜底方案 Then: 章节覆盖完整时长 [0, duration]"""
        # Arrange
        episode = Episode(
            title="Full Coverage Test",
            audio_path="/test/path.mp3",
            file_hash="test_hash",
            duration=1234.5,
            workflow_status=WorkflowStatus.TRANSCRIBED.value
        )
        test_session.add(episode)
        test_session.flush()

        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=0,
            segment_id="segment_001",
            start_time=0.0,
            end_time=1234.5,
            status="completed"
        )
        test_session.add(segment)
        test_session.flush()

        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=0.0,
            end_time=5.0,
            speaker="Speaker",
            text="Test"
        )
        test_session.add(cue)
        test_session.flush()

        service = SegmentationService(
            test_session,
            provider="moonshot",
            api_key="test_key"
        )

        with patch.object(
            service,
            '_call_ai_for_segmentation',
            side_effect=Exception("测试失败")
        ):
            # Act
            chapters = service.analyze_and_segment(episode.id)

        # Assert
        assert chapters[0].start_time == 0.0
        assert chapters[0].end_time == 1234.5
        assert chapters[0].chapter_index == 0

    def test_create_fallback_response_directly(self, test_session):
        """Given: Episode对象 When: 调用_create_fallback_response Then: 返回正确的 SegmentationResponse"""
        # Arrange
        episode = Episode(
            title="直接测试",
            audio_path="/test/path.mp3",
            file_hash="test_hash",
            duration=450.0,
            workflow_status=WorkflowStatus.TRANSCRIBED.value
        )
        test_session.add(episode)
        test_session.flush()

        service = SegmentationService(
            test_session,
            provider="moonshot",
            api_key="test_key"
        )

        # Act
        response = service._create_fallback_response(episode)

        # Assert
        assert len(response.chapters) == 1
        assert response.chapters[0].title == "直接测试"
        assert response.chapters[0].start_time == 0.0
        assert response.chapters[0].end_time == 450.0
        assert "AI 章节切分失败" in response.chapters[0].summary
        assert "7.5 分钟" in response.chapters[0].summary
