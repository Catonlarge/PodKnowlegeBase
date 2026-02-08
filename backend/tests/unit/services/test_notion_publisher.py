"""
NotionPublisher 单元测试

测试 Notion 平台发布服务：
1. validate_config() - 验证 Notion 配置
2. publish_episode() - 发布 Episode 到 Notion
3. publish_marketing_posts() - 发布营销文案到 Notion
4. create_episode_page() - 创建 Episode 页面
5. render_chapters_block() - 渲染章节表格块
6. render_transcripts_table() - 渲染字幕表格块
"""
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

import pytest

from app.services.publishers.notion import NotionPublisher
from app.models import Episode, AudioSegment, TranscriptCue, Translation, Chapter, MarketingPost
from app.enums.workflow_status import WorkflowStatus
from app.enums.translation_status import TranslationStatus


# ========================================================================
# Fixtures
# ========================================================================

@pytest.fixture
def mock_notion_client():
    """Mock Notion 客户端"""
    with patch("app.services.publishers.notion.Client") as mock:
        client = Mock()
        mock.return_value = client
        yield client


@pytest.fixture
def notion_publisher(mock_notion_client, test_session):
    """创建 NotionPublisher 实例（使用 Mock 客户端和数据库会话）"""
    return NotionPublisher(db=test_session)


@pytest.fixture
def episode_with_data(test_session):
    """创建完整的 Episode 数据（Episode + Chapters + Cues + Translations）"""
    # 创建 Episode
    episode = Episode(
        title="Test Episode: AI in 2024",
        file_hash="test_hash_2024",
        duration=600.0,
        source_url="https://youtube.com/watch?v=test123",
        ai_summary="This episode discusses AI trends in 2024.",
        workflow_status=WorkflowStatus.PUBLISHED.value
    )
    test_session.add(episode)
    test_session.flush()

    # 创建 AudioSegment
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

    # 创建 Chapters
    chapters = []
    for i in range(2):
        chapter = Chapter(
            episode_id=episode.id,
            chapter_index=i,
            title=f"Chapter {i + 1}",
            summary=f"Summary for chapter {i + 1}",
            start_time=i * 300.0,
            end_time=(i + 1) * 300.0,
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
            start_time=i * 100.0,
            end_time=(i + 1) * 100.0,
            speaker="SPEAKER_00" if i % 2 == 0 else "SPEAKER_01",
            text=f"This is sentence {i}."
        )
        # 关联到对应的 Chapter
        chapter_index = i // 3
        cue.chapter_id = chapters[chapter_index].id
        cues.append(cue)
        test_session.add(cue)
    test_session.flush()

    # 创建 Translations
    for cue in cues:
        translation = Translation(
            cue_id=cue.id,
            language_code="zh",
            translation=f"这是第 {cue.id} 句话。",
            original_translation=f"这是第 {cue.id} 句话。",
            is_edited=False,
            translation_status=TranslationStatus.COMPLETED.value
        )
        test_session.add(translation)
    test_session.flush()

    return episode


@pytest.fixture
def sample_marketing_posts(test_session, episode_with_data):
    """创建营销文案数据"""
    posts = []
    for i in range(3):
        post = MarketingPost(
            episode_id=episode_with_data.id,
            platform="xiaohongshu",
            angle_tag=f"angle_{i}",
            title=f"Post {i + 1}",
            content=f"This is marketing post content {i + 1}.",
            status="completed"
        )
        posts.append(post)
        test_session.add(post)
    test_session.flush()
    return posts


# ========================================================================
# TestInit 测试组
# ========================================================================

class TestInit:
    """测试 NotionPublisher 初始化"""

    def test_init_with_valid_config(self, mock_notion_client):
        """
        Given: 有效的 NOTION_API_KEY 和 NOTION_PARENT_PAGE_ID
        When: 创建 NotionPublisher
        Then: 对象初始化成功，client 被创建
        """
        # Arrange
        with patch("app.services.publishers.notion.NOTION_API_KEY", "test_token"):
            with patch("app.services.publishers.notion.NOTION_PARENT_PAGE_ID", "parent_page_id"):
                # Act
                publisher = NotionPublisher()

                # Assert
                assert publisher.client is not None
                assert publisher.parent_page_id == "parent_page_id"

    def test_init_without_api_key(self):
        """
        Given: NOTION_API_KEY 未设置
        When: 创建 NotionPublisher
        Then: 抛出 ValueError
        """
        # Arrange
        with patch("app.services.publishers.notion.NOTION_API_KEY", None):
            # Act & Assert
            with pytest.raises(ValueError, match="NOTION_API_KEY 未配置"):
                NotionPublisher()


# ========================================================================
# TestValidateConfig 测试组
# ========================================================================

class TestValidateConfig:
    """测试 validate_config() 方法"""

    def test_validate_config_with_valid_credentials(self, notion_publisher):
        """
        Given: 有效的 NOTION_TOKEN 和 NOTION_PARENT_PAGE_ID
        When: 调用 validate_config
        Then: 返回 True
        """
        # Arrange - Mock client.search 成功响应
        notion_publisher.client.search.return_value = {"results": []}

        # Act
        result = notion_publisher.validate_config()

        # Assert
        assert result is True
        notion_publisher.client.search.assert_called_once()

    def test_validate_config_missing_token(self):
        """
        Given: NOTION_TOKEN 未设置
        When: 创建 NotionPublisher
        Then: 抛出 ValueError
        """
        # Arrange & Act & Assert
        with patch("app.services.publishers.notion.NOTION_API_KEY", None):
            with pytest.raises(ValueError, match="NOTION_API_KEY 未配置"):
                NotionPublisher()

    def test_validate_config_api_error(self, notion_publisher):
        """
        Given: Notion API 返回错误
        When: 调用 validate_config
        Then: 返回 False
        """
        # Arrange - Mock client.search 抛出异常
        notion_publisher.client.search.side_effect = Exception("API Error")

        # Act
        result = notion_publisher.validate_config()

        # Assert
        assert result is False


# ========================================================================
# TestPublishEpisode 测试组
# ========================================================================

class TestPublishEpisode:
    """测试 publish_episode() 方法"""

    def test_publish_episode_creates_page_successfully(
        self, notion_publisher, episode_with_data, mock_notion_client
    ):
        """
        Given: Episode 和关联数据
        When: 调用 publish_episode
        Then: 调用 Notion API 创建页面，返回 PublicationRecord
        """
        # Arrange - Mock API 响应
        mock_notion_client.pages.create.return_value = {
            "id": "page_id_123",
            "url": "https://notion.so/page_id_123"
        }
        mock_notion_client.blocks.children.append.return_value = {}

        # Act
        result = notion_publisher.publish_episode(episode_with_data)

        # Assert
        assert result.status == "success"
        assert result.platform == "notion"
        assert result.platform_record_id == "page_id_123"
        assert result.episode_id == episode_with_data.id
        mock_notion_client.pages.create.assert_called()

    def test_publish_episode_creates_page_with_blocks(
        self, notion_publisher, episode_with_data, mock_notion_client
    ):
        """
        Given: Episode 包含章节和字幕
        When: 调用 publish_episode
        Then: 调用 blocks.children.append 添加内容块
        """
        # Arrange - Mock API 响应
        mock_notion_client.pages.create.return_value = {"id": "page_id_123"}
        mock_notion_client.blocks.children.append.return_value = {}

        # Act
        notion_publisher.publish_episode(episode_with_data)

        # Assert - 验证 blocks.children.append 被调用
        assert mock_notion_client.blocks.children.append.call_count > 0

    def test_publish_episode_handles_api_error(
        self, notion_publisher, episode_with_data, mock_notion_client
    ):
        """
        Given: 模拟 Notion API 错误
        When: 调用 publish_episode
        Then: 返回失败状态的 PublicationRecord
        """
        # Arrange - Mock API 错误
        mock_notion_client.pages.create.side_effect = Exception("API Error")

        # Act
        result = notion_publisher.publish_episode(episode_with_data)

        # Assert
        assert result.status == "failed"
        assert "API Error" in result.error_message
        assert result.episode_id == episode_with_data.id

    def test_publish_episode_without_chapters(
        self, notion_publisher, test_session, mock_notion_client
    ):
        """
        Given: Episode 没有 Chapter 数据
        When: 调用 publish_episode
        Then: 正常创建页面，但不包含章节导航
        """
        # Arrange - 创建没有 Chapter 的 Episode
        episode = Episode(
            title="Test Episode",
            file_hash="test_hash_no_chapters",
            duration=60.0,
            workflow_status=WorkflowStatus.PUBLISHED.value
        )
        test_session.add(episode)
        test_session.flush()

        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=0,
            segment_id="segment_001",
            start_time=0.0,
            end_time=60.0,
            status="completed"
        )
        test_session.add(segment)
        test_session.flush()

        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=0.0,
            end_time=5.0,
            text="Hello world"
        )
        test_session.add(cue)
        test_session.flush()

        translation = Translation(
            cue_id=cue.id,
            language_code="zh",
            translation="你好世界",
            original_translation="你好世界",
            is_edited=False,
            translation_status=TranslationStatus.COMPLETED.value
        )
        test_session.add(translation)
        test_session.flush()

        mock_notion_client.pages.create.return_value = {"id": "page_id_123"}
        mock_notion_client.blocks.children.append.return_value = {}

        # Act - 不应该抛出异常
        result = notion_publisher.publish_episode(episode)

        # Assert
        assert result.status == "success"


# ========================================================================
# TestCreateEpisodePage 测试组
# ========================================================================

class TestCreateEpisodePage:
    """测试 create_episode_page() 方法"""

    def test_create_episode_page_returns_page_id(
        self, notion_publisher, mock_notion_client, test_session
    ):
        """
        Given: Episode 对象和父页面 ID
        When: 调用 create_episode_page
        Then: 返回 Notion 页面 ID
        """
        # Arrange - 创建测试 Episode
        episode = Episode(
            title="Test Episode",
            file_hash="test_hash",
            duration=60.0,
            workflow_status=WorkflowStatus.PUBLISHED.value
        )
        test_session.add(episode)
        test_session.flush()

        mock_notion_client.pages.create.return_value = {"id": "page_456"}

        # Act
        page_id = notion_publisher.create_episode_page(
            episode=episode,
            parent_page_id="parent_123"
        )

        # Assert
        assert page_id == "page_456"
        mock_notion_client.pages.create.assert_called_once()

    def test_create_episode_page_with_database_parent(
        self, notion_publisher, mock_notion_client, test_session
    ):
        """
        Given: 使用 database_id 作为父节点
        When: 调用 create_episode_page
        Then: 正确设置 parent 为 database_id
        """
        # Arrange - 创建测试 Episode
        episode = Episode(
            title="Test Episode",
            file_hash="test_hash",
            duration=60.0,
            workflow_status=WorkflowStatus.PUBLISHED.value
        )
        test_session.add(episode)
        test_session.flush()

        mock_notion_client.pages.create.return_value = {"id": "page_789"}

        # Act
        page_id = notion_publisher.create_episode_page(
            episode=episode,
            parent_page_id="database_123",
            parent_type="database_id"  # Notion API 使用 database_id
        )

        # Assert
        assert page_id == "page_789"
        # 验证调用参数中包含 database_id
        call_args = mock_notion_client.pages.create.call_args
        assert "parent" in call_args[1]
        assert call_args[1]["parent"]["type"] == "database_id"


# ========================================================================
# TestRenderChaptersBlock 测试组
# ========================================================================

class TestRenderChaptersBlock:
    """测试 render_chapters_block() 方法"""

    def test_render_chapters_block_creates_navigation_list(self, notion_publisher, test_session):
        """
        Given: Chapter 列表和 Episode 对象
        When: 调用 render_chapters_block
        Then: 返回单个 callout 块，包含所有章节导航
        """
        # Arrange - 创建 Episode
        episode = Episode(
            title="Test Episode",
            file_hash="test_hash",
            duration=600.0,
            workflow_status=WorkflowStatus.PUBLISHED.value
        )
        test_session.add(episode)
        test_session.flush()

        chapters = [
            Chapter(
                id=1,
                episode_id=episode.id,
                chapter_index=0,
                title="Chapter 1",
                summary="Summary 1",
                start_time=0.0,
                end_time=300.0,
                status="completed"
            ),
            Chapter(
                id=2,
                episode_id=episode.id,
                chapter_index=1,
                title="Chapter 2",
                summary="Summary 2",
                start_time=300.0,
                end_time=600.0,
                status="completed"
            )
        ]

        # Act
        blocks = notion_publisher.render_chapters_block(chapters, episode)

        # Assert - render_chapters_block 返回单个 callout 块
        assert len(blocks) == 1
        assert blocks[0]["type"] == "callout"
        assert blocks[0]["callout"]["color"] == "blue_background"

    def test_render_chapters_block_empty_list(self, notion_publisher, test_session):
        """
        Given: 空的 Chapter 列表
        When: 调用 render_chapters_block
        Then: 返回空列表
        """
        # Arrange - 创建 Episode（即使为空也需要 episode 参数）
        episode = Episode(
            title="Test Episode",
            file_hash="test_hash",
            duration=600.0,
            workflow_status=WorkflowStatus.PUBLISHED.value
        )
        test_session.add(episode)
        test_session.flush()

        # Act
        blocks = notion_publisher.render_chapters_block([], episode)

        # Assert
        assert blocks == []

    def test_render_chapters_block_includes_summary(self, notion_publisher, test_session):
        """
        Given: Chapter 包含 summary
        When: 调用 render_chapters_block
        Then: callout 块中包含 summary 内容
        """
        # Arrange - 创建 Episode
        episode = Episode(
            title="Test Episode",
            file_hash="test_hash",
            duration=600.0,
            workflow_status=WorkflowStatus.PUBLISHED.value
        )
        test_session.add(episode)
        test_session.flush()

        chapters = [
            Chapter(
                id=1,
                episode_id=episode.id,
                chapter_index=0,
                title="Chapter 1",
                summary="Test summary content",
                start_time=0.0,
                end_time=300.0,
                status="completed"
            )
        ]

        # Act
        blocks = notion_publisher.render_chapters_block(chapters, episode)

        # Assert - 验证 callout 内容包含 summary 和章节标题
        # rich_text 现在是数组，需要遍历检查
        rich_text_items = blocks[0]["callout"]["rich_text"]
        all_content = "".join(item["text"]["content"] for item in rich_text_items)
        assert "Test summary content" in all_content
        assert "Chapter 1" in all_content

    def test_render_chapters_block_summary_not_truncated(self, notion_publisher, test_session):
        """
        Given: Chapter 包含超长 summary（超过80字符）
        When: 调用 render_chapters_block
        Then: summary 不被截断，显示完整内容（与Obsidian一致）
        """
        # Arrange - 创建 Episode
        episode = Episode(
            title="Test Episode",
            file_hash="test_hash",
            duration=600.0,
            workflow_status=WorkflowStatus.PUBLISHED.value
        )
        test_session.add(episode)
        test_session.flush()

        # 创建一个超过80字符的 summary
        long_summary = "A" * 100 + " 这是一段非常长的章节摘要，应该完整显示而不被截断，与Obsidian导出保持一致。"
        chapters = [
            Chapter(
                id=1,
                episode_id=episode.id,
                chapter_index=0,
                title="Chapter 1",
                summary=long_summary,
                start_time=0.0,
                end_time=300.0,
                status="completed"
            )
        ]

        # Act
        blocks = notion_publisher.render_chapters_block(chapters, episode)

        # Assert - 验证 summary 完整显示，没有被截断为80字符
        rich_text_items = blocks[0]["callout"]["rich_text"]
        all_content = "".join(item["text"]["content"] for item in rich_text_items)
        assert long_summary in all_content
        # 确保"..."截断标记不存在
        assert "..." not in all_content or len(all_content) >= len(long_summary)

    def test_render_chapters_block_no_timestamp_column(self, notion_publisher, test_session):
        """
        Given: Chapter 列表和 Episode 对象
        When: 调用 render_chapters_block
        Then: 不包含时间戳列
        """
        # Arrange - 创建 Episode
        episode = Episode(
            title="Test Episode",
            file_hash="test_hash",
            duration=600.0,
            workflow_status=WorkflowStatus.PUBLISHED.value
        )
        test_session.add(episode)
        test_session.flush()

        chapters = [
            Chapter(
                id=1,
                episode_id=episode.id,
                chapter_index=0,
                title="Chapter 1",
                summary="Summary 1",
                start_time=0.0,
                end_time=300.0,
                status="completed"
            )
        ]

        # Act
        blocks = notion_publisher.render_chapters_block(chapters, episode)

        # Assert - 验证不是表格格式（不包含 table 类型）
        assert not any(block.get("type") == "table" for block in blocks)


# ========================================================================
# TestRenderTranscriptsTable 测试组
# ========================================================================

class TestRenderTranscriptsTable:
    """测试 render_transcripts_table() 方法"""

    def test_render_transcripts_table_creates_speaker_grouped_blocks(self, notion_publisher):
        """
        Given: TranscriptCue 列表（同一 speaker）
        When: 调用 render_transcripts_table
        Then: 返回 speaker callout + cue callouts
        """
        # Arrange
        cues = [
            TranscriptCue(
                id=1,
                start_time=65.0,  # 1:05
                end_time=70.0,
                text="Hello world",
                speaker="SPEAKER_00"
            )
        ]
        # 模拟翻译
        cues[0].get_translation = Mock(return_value="你好世界")

        # Act
        blocks = notion_publisher.render_transcripts_table(cues, language_code="zh")

        # Assert - speaker callout + cue callout
        assert len(blocks) == 2
        assert blocks[0]["type"] == "callout"  # Speaker 标题
        assert blocks[1]["type"] == "callout"  # 字幕内容
        # Speaker 标题是蓝色背景
        assert blocks[0]["callout"]["color"] == "blue_background"
        # 字幕是灰色背景
        assert blocks[1]["callout"]["color"] == "gray_background"

    def test_render_transcripts_table_timestamp_format(self, notion_publisher):
        """
        Given: TranscriptCue 列表
        When: 调用 render_transcripts_table
        Then: 时间戳格式化为 MM:SS 并通过 annotations.bold 加粗
        """
        # Arrange
        cues = [
            TranscriptCue(
                id=1,
                start_time=65.0,  # 1:05
                end_time=70.0,
                text="Hello world",
                speaker="SPEAKER_00"
            )
        ]
        cues[0].get_translation = Mock(return_value="你好世界")

        # Act
        blocks = notion_publisher.render_transcripts_table(cues, language_code="zh")

        # Assert - 验证字幕 callout 内容结构
        cue_callout = blocks[1]
        rich_text = cue_callout["callout"]["rich_text"]

        # 时间戳是第一个元素，使用 annotations.bold 加粗
        assert rich_text[0]["text"]["content"] == "01:05"
        assert rich_text[0]["annotations"]["bold"] is True

        # 英文内容是第二个元素，不加粗（没有 annotations 键或 bold 不为 True）
        assert "Hello world" in rich_text[1]["text"]["content"]
        assert rich_text[1].get("annotations", {}).get("bold") is not True

        # 中文翻译是第三个元素（如果存在）
        assert "你好世界" in rich_text[2]["text"]["content"]

    def test_render_transcripts_table_multiple_speakers(self, notion_publisher):
        """
        Given: 多个 speaker 的 TranscriptCue
        When: 调用 render_transcripts_table
        Then: 按 speaker 分组显示
        """
        # Arrange
        cues = [
            TranscriptCue(
                id=1,
                start_time=0.0,
                end_time=5.0,
                text="First sentence",
                speaker="SPEAKER_00"
            ),
            TranscriptCue(
                id=2,
                start_time=5.0,
                end_time=10.0,
                text="Second sentence",
                speaker="SPEAKER_01"
            )
        ]
        cues[0].get_translation = Mock(return_value="第一句")
        cues[1].get_translation = Mock(return_value="第二句")

        # Act
        blocks = notion_publisher.render_transcripts_table(cues, language_code="zh")

        # Assert - 2 speakers，每个 speaker 有标题 + 字幕
        assert len(blocks) == 4  # SPEAKER_00 + cue1 + SPEAKER_01 + cue2
        # 验证 speaker 标题（保持原始格式）
        assert "SPEAKER_00" in blocks[0]["callout"]["rich_text"][0]["text"]["content"]
        assert "SPEAKER_01" in blocks[2]["callout"]["rich_text"][0]["text"]["content"]
        # 所有 block 都是 callout 类型
        assert all(block["type"] == "callout" for block in blocks)

    def test_render_transcripts_table_with_translation(self, notion_publisher):
        """
        Given: TranscriptCue 有翻译
        When: 调用 render_transcripts_table
        Then: callout 包含时间戳（加粗）、英文和中文
        """
        # Arrange
        cues = [
            TranscriptCue(
                id=1,
                start_time=0.0,
                end_time=5.0,
                text="Hello world",
                speaker="SPEAKER_00"
            )
        ]
        cues[0].get_translation = Mock(return_value="你好世界")

        # Act
        blocks = notion_publisher.render_transcripts_table(cues, language_code="zh")

        # Assert - 验证字幕 callout 内容结构
        cue_callout = blocks[1]
        rich_text = cue_callout["callout"]["rich_text"]

        # 时间戳加粗
        assert rich_text[0]["text"]["content"] == "00:00"
        assert rich_text[0]["annotations"]["bold"] is True

        # 英文内容
        assert "Hello world" in rich_text[1]["text"]["content"]

        # 中文翻译
        assert "你好世界" in rich_text[2]["text"]["content"]

    def test_render_transcripts_table_without_translation(self, notion_publisher):
        """
        Given: TranscriptCue 没有翻译
        When: 调用 render_transcripts_table
        Then: callout 只包含时间戳（加粗）和英文
        """
        # Arrange
        cues = [
            TranscriptCue(
                id=1,
                start_time=0.0,
                end_time=5.0,
                text="Hello world",
                speaker="SPEAKER_00"
            )
        ]
        cues[0].get_translation = Mock(return_value=None)

        # Act
        blocks = notion_publisher.render_transcripts_table(cues, language_code="zh")

        # Assert - 验证字幕 callout 内容结构
        cue_callout = blocks[1]
        rich_text = cue_callout["callout"]["rich_text"]

        # 只有时间戳和英文，没有翻译
        assert len(rich_text) == 2

        # 时间戳加粗
        assert rich_text[0]["text"]["content"] == "00:00"
        assert rich_text[0]["annotations"]["bold"] is True

        # 英文内容
        assert "Hello world" in rich_text[1]["text"]["content"]

    def test_render_transcripts_table_empty_cues(self, notion_publisher):
        """
        Given: 空的 TranscriptCue 列表
        When: 调用 render_transcripts_table
        Then: 返回空列表
        """
        # Act
        blocks = notion_publisher.render_transcripts_table([], language_code="zh")

        # Assert
        assert blocks == []


# ========================================================================
# TestPublishMarketingPosts 测试组
# ========================================================================

class TestPublishMarketingPosts:
    """测试 publish_marketing_posts() 方法"""

    def test_publish_marketing_posts_success(
        self, notion_publisher, sample_marketing_posts, mock_notion_client
    ):
        """
        Given: MarketingPost 列表
        When: 调用 publish_marketing_posts
        Then: 返回 PublicationRecord 列表
        """
        # Arrange - Mock API 响应
        mock_notion_client.pages.create.return_value = {"id": "page_marketing_123"}

        # Act
        results = notion_publisher.publish_marketing_posts(sample_marketing_posts)

        # Assert
        assert len(results) == 3
        assert all(r.status == "success" for r in results)
        assert all(r.platform == "notion" for r in results)

    def test_publish_marketing_posts_empty_list(self, notion_publisher):
        """
        Given: 空的 MarketingPost 列表
        When: 调用 publish_marketing_posts
        Then: 返回空列表
        """
        # Act
        results = notion_publisher.publish_marketing_posts([])

        # Assert
        assert results == []

    def test_publish_marketing_posts_handles_partial_failure(
        self, notion_publisher, sample_marketing_posts, mock_notion_client
    ):
        """
        Given: 部分发布失败
        When: 调用 publish_marketing_posts
        Then: 返回包含成功和失败状态的列表
        """
        # Arrange - Mock 第二个发布失败
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise Exception("API Error for post 2")
            return {"id": f"page_marketing_{call_count[0]}"}

        mock_notion_client.pages.create.side_effect = side_effect

        # Act
        results = notion_publisher.publish_marketing_posts(sample_marketing_posts)

        # Assert
        assert len(results) == 3
        assert results[0].status == "success"
        assert results[1].status == "failed"
        assert "API Error" in results[1].error_message
        assert results[2].status == "success"


# ========================================================================
# TestGetNotionBlockUrl 测试组
# ========================================================================

class TestFormatSpeakerName:
    """测试 _format_speaker_name() 静态方法"""

    def test_format_speaker_name_preserves_original_format(self):
        """
        Given: 原始 speaker 标识符 SPEAKER_00
        When: 调用 _format_speaker_name
        Then: 返回原始格式，与 Obsidian 一致
        """
        # Arrange
        speaker = "SPEAKER_00"

        # Act
        result = NotionPublisher._format_speaker_name(speaker)

        # Assert - 直接返回原始格式，不转换
        assert result == "SPEAKER_00"

    def test_format_speaker_name_speaker_01(self):
        """
        Given: 原始 speaker 标识符 SPEAKER_01
        When: 调用 _format_speaker_name
        Then: 返回原始格式 SPEAKER_01
        """
        # Arrange
        speaker = "SPEAKER_01"

        # Act
        result = NotionPublisher._format_speaker_name(speaker)

        # Assert
        assert result == "SPEAKER_01"


class TestGetNotionBlockUrl:
    """测试 _get_notion_block_url() 静态方法"""

    def test_get_notion_block_url_without_page_id(self):
        """
        Given: block_id 不带 page_id
        When: 调用 _get_notion_block_url
        Then: 返回格式为 https://www.notion.so/{clean_block_id}（降级格式，不带#）
        """
        # Arrange
        block_id = "abc123-def456-ghi789"

        # Act
        url = NotionPublisher._get_notion_block_url(block_id)

        # Assert - 验证 URL 格式，使用 www.notion.so，不带 # 结尾（降级格式）
        assert url.startswith("https://www.notion.so/")
        assert url == "https://www.notion.so/abc123def456ghi789"
        assert "-" not in url.split("www.notion.so/")[1]  # block_id 中的连字符被移除

    def test_get_notion_block_url_with_page_id(self):
        """
        Given: block_id 和 page_id
        When: 调用 _get_notion_block_url
        Then: 返回格式为 https://www.notion.so/{clean_page_id}#{clean_block_id}（页面内锚点格式）
        """
        # Arrange
        block_id = "block-abc-123"
        page_id = "page-def-456"

        # Act
        url = NotionPublisher._get_notion_block_url(block_id, page_id)

        # Assert - 应该使用页面内锚点格式（page_id#block_id）
        assert url.startswith("https://www.notion.so/")
        assert url == "https://www.notion.so/pagedef456#blockabc123"
        assert "pagedef456" in url  # URL 中应包含 page_id
        assert "#" in url  # 应包含锚点分隔符

    def test_get_notion_block_url_removes_hyphens(self):
        """
        Given: block_id 包含连字符
        When: 调用 _get_notion_block_url
        Then: URL 中 block_id 的连字符被移除
        """
        # Arrange
        block_id = "abc-def-ghi-jkl"

        # Act
        url = NotionPublisher._get_notion_block_url(block_id)

        # Assert
        assert "abcdefghijkl" in url
        assert "-" not in url.split("www.notion.so/")[1]  # 连字符被移除
