"""
MarketingService 摘要兜底功能测试

测试 AI 失败时使用章节小结兜底的策略。
测试 schema 验证失败时的重试机制。
"""
from unittest.mock import Mock, patch
import pytest

from app.services.marketing_service import MarketingService
from app.models import Episode, Chapter, AudioSegment, TranscriptCue, MarketingPost
from app.services.ai.schemas.marketing_schema import (
    MultiAngleMarketingResponse,
    MarketingAngle,
)
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


class TestMarketingRetryAndFallback:
    """测试 MarketingService 重试机制与兜底流程"""

    def _make_episode_with_chapters(self, test_session, title="重试测试"):
        """创建带章节小结的 Episode"""
        episode = Episode(
            title=title,
            audio_path="/test/path.mp3",
            file_hash="retry_test_hash",
            duration=300.0,
            workflow_status=WorkflowStatus.TRANSLATED.value,
        )
        test_session.add(episode)
        test_session.flush()

        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=0,
            segment_id="seg_001",
            start_time=0.0,
            end_time=300.0,
            status="completed",
        )
        test_session.add(segment)
        test_session.flush()

        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=0.0,
            end_time=10.0,
            speaker="SPEAKER_00",
            text="Test transcript for marketing.",
        )
        test_session.add(cue)
        test_session.flush()

        ch = Chapter(
            episode_id=episode.id,
            chapter_index=0,
            title="第一章",
            summary="章节小结用于兜底内容。",
            start_time=0.0,
            end_time=300.0,
        )
        test_session.add(ch)
        test_session.flush()

        return episode

    def test_generate_multi_angle_returns_fallback_when_ai_fails_after_retries(
        self, test_session
    ):
        """Given: AI 调用始终失败 When: 重试耗尽 Then: 返回章节小结兜底"""
        # Arrange
        episode = self._make_episode_with_chapters(test_session)
        service = MarketingService(
            test_session, provider="moonshot", api_key="test_key"
        )

        mock_invoke = Mock(side_effect=ValueError("schema validation failed"))
        service.structured_llm = Mock()
        service.structured_llm.with_structured_output.return_value.invoke = (
            mock_invoke
        )

        # Act
        result = service.generate_xiaohongshu_copy_multi_angle(episode.id)

        # Assert
        assert len(result) == 1
        assert result[0].content == "章节小结用于兜底内容。"
        assert result[0].metadata["fallback"] is True
        assert mock_invoke.call_count == 2

    def test_generate_multi_angle_retries_then_succeeds_on_second_attempt(
        self, test_session
    ):
        """Given: 首次 AI 调用失败 When: 第二次成功 Then: 返回 AI 结果而非兜底"""
        # Arrange
        episode = self._make_episode_with_chapters(test_session)
        service = MarketingService(
            test_session, provider="moonshot", api_key="test_key"
        )

        valid_response = MultiAngleMarketingResponse(
            angles=[
                MarketingAngle(
                    angle_name="角度一",
                    title="测试标题一",
                    content="x" * 200,
                    hashtags=["#测试", "#播客", "#学习"],
                ),
                MarketingAngle(
                    angle_name="角度二",
                    title="测试标题二",
                    content="y" * 200,
                    hashtags=["#测试", "#播客", "#学习"],
                ),
                MarketingAngle(
                    angle_name="角度三",
                    title="测试标题三",
                    content="z" * 200,
                    hashtags=["#测试", "#播客", "#学习"],
                ),
            ]
        )

        mock_invoke = Mock(
            side_effect=[ValueError("schema fail"), valid_response]
        )
        service.structured_llm = Mock()
        service.structured_llm.with_structured_output.return_value.invoke = (
            mock_invoke
        )

        # Act
        result = service.generate_xiaohongshu_copy_multi_angle(episode.id)

        # Assert
        assert len(result) == 3
        assert result[0].metadata.get("angle_tag") == "角度一"
        assert "fallback" not in result[0].metadata
        assert mock_invoke.call_count == 2


class TestMarketingDeleteAndForceRemarketing:
    """测试 MarketingService 删除旧文案与强制重新生成"""

    def test_delete_marketing_posts_removes_existing_posts(self, test_session):
        """Given: Episode 有 2 条营销文案 When: 调用 delete_marketing_posts_for_episode Then: 全部删除并返回 2"""
        # Arrange
        episode = Episode(
            title="删除测试",
            audio_path="/test/path.mp3",
            file_hash="del_test_hash",
            duration=300.0,
            workflow_status=WorkflowStatus.TRANSLATED.value,
        )
        test_session.add(episode)
        test_session.flush()

        post1 = MarketingPost(
            episode_id=episode.id,
            platform="xhs",
            angle_tag="角度1",
            title="标题1",
            content="内容1",
        )
        post2 = MarketingPost(
            episode_id=episode.id,
            platform="xhs",
            angle_tag="角度2",
            title="标题2",
            content="内容2",
        )
        test_session.add_all([post1, post2])
        test_session.flush()

        service = MarketingService(
            test_session, provider="moonshot", api_key="test_key"
        )

        # Act
        count = service.delete_marketing_posts_for_episode(episode.id)
        test_session.commit()

        # Assert
        assert count == 2
        remaining = test_session.query(MarketingPost).filter(
            MarketingPost.episode_id == episode.id
        ).count()
        assert remaining == 0

    def test_delete_marketing_posts_returns_zero_when_no_posts(self, test_session):
        """Given: Episode 无营销文案 When: 调用 delete_marketing_posts_for_episode Then: 返回 0"""
        # Arrange
        episode = Episode(
            title="无文案测试",
            audio_path="/test/path.mp3",
            file_hash="no_post_hash",
            duration=300.0,
            workflow_status=WorkflowStatus.TRANSLATED.value,
        )
        test_session.add(episode)
        test_session.flush()

        service = MarketingService(
            test_session, provider="moonshot", api_key="test_key"
        )

        # Act
        count = service.delete_marketing_posts_for_episode(episode.id)

        # Assert
        assert count == 0

    def test_delete_marketing_posts_does_not_affect_other_episodes(self, test_session):
        """Given: Episode A 有文案，Episode B 无文案 When: 删除 A 的文案 Then: B 不受影响"""
        # Arrange
        ep_a = Episode(
            title="A",
            audio_path="/a.mp3",
            file_hash="hash_a",
            duration=300.0,
            workflow_status=WorkflowStatus.TRANSLATED.value,
        )
        ep_b = Episode(
            title="B",
            audio_path="/b.mp3",
            file_hash="hash_b",
            duration=300.0,
            workflow_status=WorkflowStatus.TRANSLATED.value,
        )
        test_session.add_all([ep_a, ep_b])
        test_session.flush()

        post_b = MarketingPost(
            episode_id=ep_b.id,
            platform="xhs",
            angle_tag="B角度",
            title="B标题",
            content="B内容",
        )
        test_session.add(post_b)
        test_session.flush()

        service = MarketingService(
            test_session, provider="moonshot", api_key="test_key"
        )

        # Act
        service.delete_marketing_posts_for_episode(ep_a.id)
        test_session.commit()

        # Assert
        post_b_after = test_session.get(MarketingPost, post_b.id)
        assert post_b_after is not None
        assert post_b_after.episode_id == ep_b.id
