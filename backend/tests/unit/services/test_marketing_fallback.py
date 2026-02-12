"""
MarketingService 摘要兜底功能测试

测试 AI 失败时使用章节小结兜底的策略。
"""
from unittest.mock import Mock
import pytest

from app.services.marketing_service import MarketingService
from app.models import Episode, Chapter
from app.enums.workflow_status import WorkflowStatus


class TestMarketingFallback:
    """测试 MarketingService 章节小结兜底功能"""

    def test_fallback_uses_chapter_summaries(self, test_session):
        """Given: Episode有章节小结 When: 调用兜底方法 Then: 内容使用所有章节小结拼接"""
        # Arrange
        episode = Episode(
            title="测试标题",
            audio_path="/test/path.mp3",
            file_hash="test_hash",
            duration=300.0,
            workflow_status=WorkflowStatus.TRANSLATED.value
        )
        test_session.add(episode)
        test_session.flush()

        ch1 = Chapter(
            episode_id=episode.id,
            chapter_index=0,
            title="第一章",
            summary="这是第一章的小结，包含核心内容。",
            start_time=0.0,
            end_time=300.0,
        )
        ch2 = Chapter(
            episode_id=episode.id,
            chapter_index=1,
            title="第二章",
            summary="这是第二章的小结。",
            start_time=300.0,
            end_time=600.0,
        )
        test_session.add_all([ch1, ch2])
        test_session.flush()

        service = MarketingService(
            test_session,
            provider="moonshot",
            api_key="test_key"
        )

        key_quotes = ["金句1", "金句2"]

        # Act - 直接调用兜底方法
        result = service._generate_fallback_multi_angle_copy(episode, key_quotes)

        # Assert
        assert len(result) == 1
        assert result[0].content == "这是第一章的小结，包含核心内容。\n\n这是第二章的小结。"
        assert result[0].title == "测试标题"
        assert result[0].hashtags == ["#播客", "#学习", "#英语"]
        assert result[0].metadata["angle_tag"] == "默认"
        assert result[0].metadata["fallback"] is True

    def test_fallback_uses_title_when_no_chapter_summaries(self, test_session):
        """Given: 无章节 When: 调用兜底方法 Then: 内容使用 episode.title"""
        # Arrange
        episode = Episode(
            title="备用标题内容",
            audio_path="/test/path.mp3",
            file_hash="test_hash",
            duration=300.0,
            workflow_status=WorkflowStatus.TRANSLATED.value
        )
        test_session.add(episode)
        test_session.flush()

        service = MarketingService(
            test_session,
            provider="moonshot",
            api_key="test_key"
        )

        # Act
        result = service._generate_fallback_multi_angle_copy(episode, [])

        # Assert
        assert len(result) == 1
        assert result[0].content == "备用标题内容"
        assert result[0].title == "备用标题内容"

    def test_fallback_uses_title_when_chapters_have_no_summary(self, test_session):
        """Given: 有章节但 summary 全为空 When: 调用兜底方法 Then: 内容使用 episode.title"""
        # Arrange
        episode = Episode(
            title="无小结标题",
            audio_path="/test/path.mp3",
            file_hash="test_hash",
            duration=300.0,
            workflow_status=WorkflowStatus.TRANSLATED.value
        )
        test_session.add(episode)
        test_session.flush()

        ch = Chapter(
            episode_id=episode.id,
            chapter_index=0,
            title="第一章",
            summary=None,
            start_time=0.0,
            end_time=300.0,
        )
        test_session.add(ch)
        test_session.flush()

        service = MarketingService(
            test_session,
            provider="moonshot",
            api_key="test_key"
        )

        # Act
        result = service._generate_fallback_multi_angle_copy(episode, [])

        # Assert
        assert len(result) == 1
        assert result[0].content == "无小结标题"

    def test_fallback_title_truncated_when_too_long(self, test_session):
        """Given: 标题超过30字符 When: 调用兜底方法 Then: 标题截取到30字符"""
        # Arrange
        long_title = "这是一个非常非常长的标题超过三十个字符的限制"
        episode = Episode(
            title=long_title,
            audio_path="/test/path.mp3",
            file_hash="test_hash",
            duration=300.0,
            workflow_status=WorkflowStatus.TRANSLATED.value
        )
        test_session.add(episode)
        test_session.flush()

        ch = Chapter(
            episode_id=episode.id,
            chapter_index=0,
            title="章",
            summary="章节小结内容",
            start_time=0.0,
            end_time=300.0,
        )
        test_session.add(ch)
        test_session.flush()

        service = MarketingService(
            test_session,
            provider="moonshot",
            api_key="test_key"
        )

        # Act
        result = service._generate_fallback_multi_angle_copy(episode, [])

        # Assert
        assert len(result[0].title) <= 30
        assert result[0].title == long_title[:30]

    def test_fallback_preserves_key_quotes(self, test_session):
        """Given: 有金句列表 When: 调用兜底方法 Then: 金句被保留"""
        # Arrange
        episode = Episode(
            title="金句测试",
            audio_path="/test/path.mp3",
            file_hash="test_hash",
            duration=300.0,
            workflow_status=WorkflowStatus.TRANSLATED.value
        )
        test_session.add(episode)
        test_session.flush()

        ch = Chapter(
            episode_id=episode.id,
            chapter_index=0,
            title="章",
            summary="摘要",
            start_time=0.0,
            end_time=300.0,
        )
        test_session.add(ch)
        test_session.flush()

        service = MarketingService(
            test_session,
            provider="moonshot",
            api_key="test_key"
        )

        key_quotes = ["金句A", "金句B", "金句C"]

        # Act
        result = service._generate_fallback_multi_angle_copy(episode, key_quotes)

        # Assert
        assert len(result) == 1
        assert result[0].key_quotes == key_quotes
