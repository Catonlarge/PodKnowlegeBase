"""
MarketingService 单元测试

测试小红书风格营销文案生成服务
"""
import json
from unittest.mock import Mock, patch

import pytest

from app.services.marketing_service import MarketingService
from app.models import Episode, AudioSegment, TranscriptCue, Translation, Chapter, MarketingPost
from app.enums.workflow_status import WorkflowStatus
from app.enums.translation_status import TranslationStatus


class TestExtractKeyQuotes:
    """测试金句提取功能"""

    def test_extract_key_quotes_from_summary(self, test_session):
        """
        Given: Episode 包含 ai_summary
        When: 调用 extract_key_quotes()
        Then: 返回 5 条金句
        """
        # Arrange
        episode = Episode(
            title="Test Episode",
            file_hash="test123",
            duration=100.0,
            ai_summary="这是第一句重要的话。这是第二句有洞察的观点。第三句是情感共鸣的内容。第四句提供了实用建议。第五句总结了核心思想。"
        )
        test_session.add(episode)
        test_session.flush()

        marketing_service = MarketingService(test_session, llm_service=Mock())

        # Act
        quotes = marketing_service.extract_key_quotes(episode.id, max_quotes=5)

        # Assert
        assert len(quotes) == 5
        # 验证每条金句都是字符串
        for quote in quotes:
            assert isinstance(quote, str)
            assert len(quote) > 0

    def test_extract_key_quotes_custom_limit(self, test_session):
        """
        Given: Episode 包含大量内容
        When: 调用 extract_key_quotes(max_quotes=3)
        Then: 只返回 3 条金句
        """
        # Arrange
        episode = Episode(
            title="Test Episode",
            file_hash="test123",
            duration=100.0,
            ai_summary="第一句。第二句。第三句。第四句。第五句。"
        )
        test_session.add(episode)
        test_session.flush()

        marketing_service = MarketingService(test_session, llm_service=Mock())

        # Act
        quotes = marketing_service.extract_key_quotes(episode.id, max_quotes=3)

        # Assert
        assert len(quotes) == 3

    def test_extract_key_quotes_episode_not_found(self, test_session):
        """
        Given: 不存在的 episode_id
        When: 调用 extract_key_quotes()
        Then: 抛出 ValueError
        """
        # Arrange
        marketing_service = MarketingService(test_session, llm_service=Mock())

        # Act & Assert
        with pytest.raises(ValueError, match="Episode not found"):
            marketing_service.extract_key_quotes(99999)


class TestGenerateTitles:
    """测试标题生成功能"""

    @patch('app.services.marketing_service.MarketingService._call_llm_for_titles')
    def test_generate_titles_returns_multiple(self, mock_llm, test_session):
        """
        Given: Episode 数据
        When: 调用 generate_titles(count=5)
        Then: 返回 5 个标题
        """
        # Arrange
        episode = Episode(
            title="Test Episode About AI",
            file_hash="test123",
            duration=100.0,
            ai_summary="关于AI的讨论"
        )
        test_session.add(episode)
        test_session.flush()

        mock_llm.return_value = [
            "标题1: AI改变世界",
            "标题2: 人工智能的未来",
            "标题3: 你需要知道的AI知识",
            "标题4: AI如何影响生活",
            "标题5: 深入了解人工智能"
        ]

        marketing_service = MarketingService(test_session, llm_service=Mock())

        # Act
        titles = marketing_service.generate_titles(episode.id, count=5)

        # Assert
        assert len(titles) == 5
        # 验证每个标题都是字符串且非空
        for title in titles:
            assert isinstance(title, str)
            assert len(title) > 0

    @patch('app.services.marketing_service.MarketingService._call_llm_for_titles')
    def test_generate_titles_no_duplicates(self, mock_llm, test_session):
        """
        Given: Episode 数据
        When: 调用 generate_titles()
        Then: 返回的标题无重复
        """
        # Arrange
        episode = Episode(
            title="Test Episode",
            file_hash="test123",
            duration=100.0,
            ai_summary="测试内容"
        )
        test_session.add(episode)
        test_session.flush()

        mock_llm.return_value = [
            "标题1",
            "标题2",
            "标题3",
            "标题4",
            "标题5"
        ]

        marketing_service = MarketingService(test_session, llm_service=Mock())

        # Act
        titles = marketing_service.generate_titles(episode.id, count=5)

        # Assert
        assert len(titles) == len(set(titles))  # 无重复

    def test_generate_titles_episode_not_found(self, test_session):
        """
        Given: 不存在的 episode_id
        When: 调用 generate_titles()
        Then: 抛出 ValueError
        """
        # Arrange
        marketing_service = MarketingService(test_session, llm_service=Mock())

        # Act & Assert
        with pytest.raises(ValueError, match="Episode not found"):
            marketing_service.generate_titles(99999)


class TestGenerateHashtags:
    """测试标签生成功能"""

    @patch('app.services.marketing_service.MarketingService._call_llm_for_hashtags')
    def test_generate_hashtags_with_hash_prefix(self, mock_llm, test_session):
        """
        Given: Episode 数据
        When: 调用 generate_hashtags()
        Then: 所有标签带 # 前缀
        """
        # Arrange
        episode = Episode(
            title="AI Technology Episode",
            file_hash="test123",
            duration=100.0,
            ai_summary="关于人工智能的讨论"
        )
        test_session.add(episode)
        test_session.flush()

        mock_llm.return_value = [
            "#人工智能",
            "#AI技术",
            "#科技前沿",
            "#学习干货",
            "#知识分享"
        ]

        marketing_service = MarketingService(test_session, llm_service=Mock())

        # Act
        hashtags = marketing_service.generate_hashtags(episode.id, max_tags=5)

        # Assert
        assert len(hashtags) == 5
        # 验证所有标签带 # 前缀
        for tag in hashtags:
            assert tag.startswith("#")
            assert len(tag) > 1

    @patch('app.services.marketing_service.MarketingService._call_llm_for_hashtags')
    def test_generate_hashtags_custom_limit(self, mock_llm, test_session):
        """
        Given: Episode 数据
        When: 调用 generate_hashtags(max_tags=3)
        Then: 只返回 3 个标签
        """
        # Arrange
        episode = Episode(
            title="Test Episode",
            file_hash="test123",
            duration=100.0,
            ai_summary="测试内容"
        )
        test_session.add(episode)
        test_session.flush()

        mock_llm.return_value = ["#标签1", "#标签2", "#标签3"]

        marketing_service = MarketingService(test_session, llm_service=Mock())

        # Act
        hashtags = marketing_service.generate_hashtags(episode.id, max_tags=3)

        # Assert
        assert len(hashtags) == 3


class TestGenerateXiaohongshuCopy:
    """测试小红书文案生成"""

    @patch('app.services.marketing_service.MarketingService._call_llm_for_xiaohongshu_content')
    @patch('app.services.marketing_service.MarketingService.generate_titles')
    @patch('app.services.marketing_service.MarketingService.generate_hashtags')
    @patch('app.services.marketing_service.MarketingService.extract_key_quotes')
    def test_generate_xiaohongshu_copy_structure(
        self, mock_quotes, mock_hashtags, mock_titles, mock_content, test_session
    ):
        """
        Given: Episode 数据
        When: 调用 generate_xiaohongshu_copy()
        Then: 返回符合小红书风格的文案
        """
        # Arrange
        episode = Episode(
            title="AI Technology Episode",
            file_hash="test123",
            duration=100.0,
            ai_summary="关于人工智能的深度讨论"
        )
        test_session.add(episode)
        test_session.flush()

        mock_quotes.return_value = ["金句1", "金句2"]
        mock_hashtags.return_value = ["#AI", "#科技"]
        mock_titles.return_value = ["标题1"]
        mock_content.return_value = "宝子们！今天分享...\n\n✅ 要点1\n✅ 要点2\n\n真的太有用了！"

        marketing_service = MarketingService(test_session, llm_service=Mock())

        # Act
        result = marketing_service.generate_xiaohongshu_copy(episode.id)

        # Assert
        assert result.title == "标题1"
        assert "宝子们" in result.content
        assert result.hashtags == ["#AI", "#科技"]
        assert result.key_quotes == ["金句1", "金句2"]

    @patch('app.services.marketing_service.MarketingService._call_llm_for_xiaohongshu_content')
    @patch('app.services.marketing_service.MarketingService.generate_titles')
    @patch('app.services.marketing_service.MarketingService.generate_hashtags')
    @patch('app.services.marketing_service.MarketingService.extract_key_quotes')
    def test_generate_xiaohongshu_copy_with_emoji(
        self, mock_quotes, mock_hashtags, mock_titles, mock_content, test_session
    ):
        """
        Given: Episode 数据
        When: 生成小红书文案
        Then: 内容包含 emoji
        """
        # Arrange
        episode = Episode(
            title="Test Episode",
            file_hash="test123",
            duration=100.0,
            ai_summary="测试内容"
        )
        test_session.add(episode)
        test_session.flush()

        mock_quotes.return_value = []
        mock_hashtags.return_value = ["#测试"]
        mock_titles.return_value = ["🎯 测试标题"]
        mock_content.return_value = "✅ 内容1\n💡 内容2\n🎉 内容3"

        marketing_service = MarketingService(test_session, llm_service=Mock())

        # Act
        result = marketing_service.generate_xiaohongshu_copy(episode.id)

        # Assert - 验证包含 emoji
        emoji_chars = ["✅", "💡", "🎉", "🎯"]
        has_emoji = any(e in result.content for e in emoji_chars)
        assert has_emoji, "Content should contain emoji"

    @patch('app.services.marketing_service.MarketingService._call_llm_for_xiaohongshu_content')
    @patch('app.services.marketing_service.MarketingService.generate_titles')
    @patch('app.services.marketing_service.MarketingService.generate_hashtags')
    @patch('app.services.marketing_service.MarketingService.extract_key_quotes')
    def test_generate_xiaohongshu_copy_with_call_to_action(
        self, mock_quotes, mock_hashtags, mock_titles, mock_content, test_session
    ):
        """
        Given: Episode 数据
        When: 生成小红书文案
        Then: 结尾包含 CTA（点赞收藏关注）
        """
        # Arrange
        episode = Episode(
            title="Test Episode",
            file_hash="test123",
            duration=100.0,
            ai_summary="测试内容"
        )
        test_session.add(episode)
        test_session.flush()

        mock_quotes.return_value = []
        mock_hashtags.return_value = ["#测试"]
        mock_titles.return_value = ["标题"]
        mock_content.return_value = "内容...\n\n点赞收藏关注我，不错过更多干货！"

        marketing_service = MarketingService(test_session, llm_service=Mock())

        # Act
        result = marketing_service.generate_xiaohongshu_copy(episode.id)

        # Assert - 验证包含 CTA
        assert "点赞" in result.content or "收藏" in result.content or "关注" in result.content

    def test_generate_xiaohongshu_copy_episode_not_found(self, test_session):
        """
        Given: 不存在的 episode_id
        When: 调用 generate_xiaohongshu_copy()
        Then: 抛出 ValueError
        """
        # Arrange
        marketing_service = MarketingService(test_session, llm_service=Mock())

        # Act & Assert
        with pytest.raises(ValueError, match="Episode not found"):
            marketing_service.generate_xiaohongshu_copy(99999)


class TestMarketingCopyDataPersistence:
    """测试文案持久化"""

    def test_save_marketing_copy_to_database(self, test_session):
        """
        Given: 生成的营销文案
        When: 调用 save_marketing_copy()
        Then: 文案被保存到数据库
        """
        # Arrange
        episode = Episode(
            title="Test Episode",
            file_hash="test123",
            duration=100.0,
        )
        test_session.add(episode)
        test_session.flush()

        marketing_service = MarketingService(test_session, llm_service=Mock())

        from dataclasses import dataclass, field
        from typing import List, Dict, Any

        @dataclass
        class MarketingCopy:
            title: str
            content: str
            hashtags: List[str]
            key_quotes: List[str]
            metadata: Dict[str, Any] = field(default_factory=dict)

        copy = MarketingCopy(
            title="测试标题",
            content="测试内容",
            hashtags=["#测试1", "#测试2"],
            key_quotes=["金句1"]
        )

        # Act
        post = marketing_service.save_marketing_copy(
            episode_id=episode.id,
            copy=copy,
            platform="xhs",
            angle_tag="测试角度"
        )

        # Assert
        test_session.flush()
        assert post.id is not None
        assert post.episode_id == episode.id
        assert post.title == "测试标题"
        assert post.content == "测试内容"
        assert post.platform == "xhs"
        assert post.angle_tag == "测试角度"

    def test_load_marketing_copy_from_database(self, test_session):
        """
        Given: 数据库中的营销文案
        When: 调用 load_marketing_copy()
        Then: 正确加载文案数据
        """
        # Arrange
        episode = Episode(
            title="Test Episode",
            file_hash="test123",
            duration=100.0,
        )
        test_session.add(episode)
        test_session.flush()

        post = MarketingPost(
            episode_id=episode.id,
            platform="xhs",
            angle_tag="测试角度",
            title="测试标题",
            content="测试内容",
            status="pending"
        )
        test_session.add(post)
        test_session.flush()

        marketing_service = MarketingService(test_session, llm_service=Mock())

        # Act
        loaded_post = marketing_service.load_marketing_copy(post.id)

        # Assert
        assert loaded_post.id == post.id
        assert loaded_post.title == "测试标题"
        assert loaded_post.content == "测试内容"
        assert loaded_post.platform == "xhs"
