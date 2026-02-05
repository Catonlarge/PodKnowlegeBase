"""
MarketingService 集成测试

测试完整的营销文案生成-保存-加载流程
"""
from unittest.mock import Mock

import pytest

from app.services.marketing_service import MarketingService
from app.models import Episode, AudioSegment, TranscriptCue, Translation, Chapter, MarketingPost
from app.enums.workflow_status import WorkflowStatus
from app.enums.translation_status import TranslationStatus


@pytest.fixture
def full_episode_data(test_session):
    """创建完整的 Episode 数据用于集成测试"""
    # 创建 Episode
    episode = Episode(
        title="Integration Test Episode for Marketing",
        file_hash="integration_marketing_test_hash",
        duration=300.0,
        source_url="https://youtube.com/watch?v=integration_marketing_test",
        ai_summary="This is an integration test episode for marketing copy generation. It contains several key points about AI and technology. The discussion covers deep learning applications. There are insights about future trends.",
        workflow_status=WorkflowStatus.TRANSLATED.value
    )
    test_session.add(episode)
    test_session.flush()

    # 创建 AudioSegment
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

    # 创建 Chapters
    chapters = []
    for i in range(2):
        chapter = Chapter(
            episode_id=episode.id,
            chapter_index=i,
            title=f"Chapter {i + 1}",
            summary=f"Summary for chapter {i + 1}",
            start_time=i * 150.0,
            end_time=(i + 1) * 150.0,
            status="completed"
        )
        chapters.append(chapter)
        test_session.add(chapter)
    test_session.flush()

    # 创建 TranscriptCue 并关联到 Chapters
    cues = []
    for i in range(6):
        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=i * 50.0,
            end_time=(i + 1) * 50.0,
            speaker="SPEAKER_00" if i % 2 == 0 else "SPEAKER_01",
            text=f"This is a longer test sentence with more content for key quote extraction. Sentence number {i}."
        )
        # 关联到对应的 Chapter
        chapter_index = 0 if i < 3 else 1
        cue.chapter_id = chapters[chapter_index].id
        cues.append(cue)
        test_session.add(cue)
    test_session.flush()

    # 创建 Translations
    for cue in cues:
        translation = Translation(
            cue_id=cue.id,
            language_code="zh",
            translation=f"这是测试句子 {cue.id} 的翻译内容。",
            original_translation=f"这是测试句子 {cue.id} 的翻译内容。",
            is_edited=False,
            translation_status=TranslationStatus.COMPLETED.value
        )
        test_session.add(translation)
    test_session.flush()

    return episode


class TestMarketingIntegration:
    """MarketingService 集成测试"""

    def test_full_marketing_workflow(self, full_episode_data, test_session):
        """
        Given: 完整的 Episode 数据
        When:
            1. 提取金句
            2. 生成标题
            3. 生成标签
            4. 生成小红书文案
            5. 保存到数据库
            6. 从数据库加载
        Then:
            1. 所有数据正确生成
            2. 数据库保存成功
            3. 可以重新加载使用
        """
        # Arrange
        service = MarketingService(test_session, llm_service=Mock())
        episode_id = full_episode_data.id

        # Act 1: 提取金句
        quotes = service.extract_key_quotes(episode_id, max_quotes=5)

        # Assert 1: 验证金句
        assert len(quotes) > 0
        assert all(isinstance(q, str) for q in quotes)
        assert all(len(q) > 0 for q in quotes)

        # Act 2: 生成标题
        titles = service.generate_titles(episode_id, count=5)

        # Assert 2: 验证标题
        assert len(titles) == 5
        assert all(isinstance(t, str) for t in titles)
        # 验证无重复
        assert len(titles) == len(set(titles))

        # Act 3: 生成标签
        hashtags = service.generate_hashtags(episode_id, max_tags=10)

        # Assert 3: 验证标签
        assert len(hashtags) > 0
        assert all(tag.startswith("#") for tag in hashtags)

        # Act 4: 生成小红书文案
        marketing_copy = service.generate_xiaohongshu_copy(episode_id)

        # Assert 4: 验证文案结构
        assert marketing_copy.title is not None
        assert len(marketing_copy.title) > 0
        assert marketing_copy.content is not None
        assert len(marketing_copy.content) > 0
        assert marketing_copy.hashtags is not None
        assert len(marketing_copy.hashtags) > 0
        assert marketing_copy.key_quotes is not None
        assert len(marketing_copy.key_quotes) > 0

        # 验证小红书风格特征
        assert "宝子们" in marketing_copy.content
        assert any(emoji in marketing_copy.content for emoji in ["✅", "💡", "🔥", "✨"])
        assert "点赞" in marketing_copy.content or "收藏" in marketing_copy.content or "关注" in marketing_copy.content

        # Act 5: 保存到数据库
        post = service.save_marketing_copy(
            episode_id=episode_id,
            copy=marketing_copy,
            platform="xhs",
            angle_tag="测试角度"
        )

        # Assert 5: 验证数据库记录
        test_session.flush()
        assert post.id is not None
        assert post.episode_id == episode_id
        assert post.platform == "xhs"
        assert post.angle_tag == "测试角度"
        assert post.title == marketing_copy.title
        assert post.content == marketing_copy.content
        assert post.status == "pending"

        # Act 6: 从数据库加载
        loaded_post = service.load_marketing_copy(post.id)

        # Assert 6: 验证加载的数据
        assert loaded_post is not None
        assert loaded_post.id == post.id
        assert loaded_post.title == marketing_copy.title
        assert loaded_post.content == marketing_copy.content

    def test_generate_multiple_copies_for_same_episode(self, full_episode_data, test_session):
        """
        Given: 完整的 Episode 数据
        When: 为同一 Episode 生成多个不同角度的文案
        Then: 所有文案都正确保存到数据库
        """
        # Arrange
        service = MarketingService(test_session, llm_service=Mock())
        episode_id = full_episode_data.id

        # Act - 生成 3 个不同角度的文案
        angles = ["干货硬核向", "轻松有趣向", "深度思考向"]
        posts = []

        for angle in angles:
            marketing_copy = service.generate_xiaohongshu_copy(episode_id)
            post = service.save_marketing_copy(
                episode_id=episode_id,
                copy=marketing_copy,
                platform="xhs",
                angle_tag=angle
            )
            posts.append(post)

        test_session.flush()

        # Assert - 验证所有文案都保存成功
        assert len(posts) == 3
        assert all(p.id is not None for p in posts)
        assert all(p.episode_id == episode_id for p in posts)
        assert all(p.platform == "xhs" for p in posts)

        # 验证每个文案有不同的角度标签
        saved_angles = [p.angle_tag for p in posts]
        assert set(saved_angles) == set(angles)

        # 验证数据库中确实有 3 条记录
        count = test_session.query(MarketingPost).filter(
            MarketingPost.episode_id == episode_id
        ).count()
        assert count == 3

    def test_marketing_copy_with_chapter_focus(self, full_episode_data, test_session):
        """
        Given: 包含多个 Chapter 的 Episode
        When: 为特定 Chapter 生成营销文案
        Then: 文案正确保存并关联到 Chapter
        """
        # Arrange
        service = MarketingService(test_session, llm_service=Mock())
        episode_id = full_episode_data.id

        # 获取第一个 Chapter
        chapter = test_session.query(Chapter).filter(
            Chapter.episode_id == episode_id
        ).first()

        # Act
        marketing_copy = service.generate_xiaohongshu_copy(episode_id)
        post = service.save_marketing_copy(
            episode_id=episode_id,
            copy=marketing_copy,
            platform="xhs",
            angle_tag=f"章节{chapter.chapter_index + 1}重点"
        )

        # 手动关联到 Chapter（通过更新记录）
        post.chapter_id = chapter.id
        test_session.flush()

        # Assert
        test_session.refresh(post)
        assert post.chapter_id == chapter.id
        assert post.episode_id == episode_id

    def test_marketing_service_with_empty_summary(self, test_session):
        """
        Given: Episode 没有 ai_summary
        When: 生成营销文案
        Then: 从 TranscriptCue 中提取金句，不抛出异常
        """
        # Arrange
        episode = Episode(
            title="No Summary Episode",
            file_hash="no_summary_hash",
            duration=100.0,
            ai_summary=None,  # 没有 summary
            workflow_status=WorkflowStatus.TRANSLATED.value
        )
        test_session.add(episode)
        test_session.flush()

        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=0,
            segment_id="segment_001",
            start_time=0.0,
            end_time=100.0,
            status="completed"
        )
        test_session.add(segment)
        test_session.flush()

        # 添加一些较长的字幕
        for i in range(5):
            cue = TranscriptCue(
                segment_id=segment.id,
                start_time=i * 20.0,
                end_time=(i + 1) * 20.0,
                text=f"This is a longer test sentence with enough content for key quote extraction at position {i}."
            )
            test_session.add(cue)
        test_session.flush()

        service = MarketingService(test_session, llm_service=Mock())

        # Act - 不应该抛出异常
        quotes = service.extract_key_quotes(episode.id, max_quotes=3)

        # Assert - 应该从字幕中提取金句
        assert len(quotes) > 0
        assert all(isinstance(q, str) for q in quotes)

    def test_marketing_copy_content_richness(self, full_episode_data, test_session):
        """
        Given: 完整的 Episode 数据
        When: 生成小红书文案
        Then: 文案内容丰富，包含多个元素
        """
        # Arrange
        service = MarketingService(test_session, llm_service=Mock())

        # Act
        marketing_copy = service.generate_xiaohongshu_copy(full_episode_data.id)

        # Assert - 验证内容丰富性
        # 1. 标题包含吸引人的元素
        assert any(emoji in marketing_copy.title for emoji in ["🎯", "💡", "🔥", "✨", "📚"])

        # 2. 正文包含多个部分
        content_lines = marketing_copy.content.split('\n')
        assert len(content_lines) > 5  # 应该有多行内容

        # 3. 包含 emoji 元素
        emoji_count = sum(1 for c in marketing_copy.content if ord(c) > 0x1F300 and ord(c) < 0x1FA00)
        assert emoji_count > 0

        # 4. 包含标签
        assert len(marketing_copy.hashtags) > 0
        assert all(tag.startswith("#") for tag in marketing_copy.hashtags)

        # 5. 包含金句
        assert len(marketing_copy.key_quotes) > 0
