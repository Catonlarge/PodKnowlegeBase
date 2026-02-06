"""
NotionPublisher 集成测试（真实 Notion API）

测试 NotionPublisher 与真实 Notion API 的集成：
1. 验证 API 连接
2. 创建测试页面
3. 发布 Episode 内容

注意：此测试需要配置真实的 NOTION_API_KEY 和 NOTION_PARENT_PAGE_ID
"""
import io
import os
import sys
from datetime import datetime

# Windows UTF-8 编码处理
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.services.publishers.notion import NotionPublisher
from app.models import Episode, AudioSegment, TranscriptCue, Translation, Chapter, Base
from app.enums.workflow_status import WorkflowStatus
from app.enums.translation_status import TranslationStatus
from app.config import NOTION_API_KEY, NOTION_PARENT_PAGE_ID


# ========================================================================
# 集成测试标记
# ========================================================================

def requires_notion_config():
    """检查是否配置了 Notion API"""
    return pytest.mark.skipif(
        not NOTION_API_KEY or not NOTION_PARENT_PAGE_ID,
        reason="需要 NOTION_API_KEY 和 NOTION_PARENT_PAGE_ID 环境变量"
    )


# ========================================================================
# 测试数据库设置
# ========================================================================

@pytest.fixture(scope="function")
def integration_db():
    """创建内存数据库用于集成测试"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    yield session

    session.close()
    engine.dispose()


@pytest.fixture(scope="function")
def integration_episode(integration_db):
    """创建集成测试用的 Episode 数据"""
    episode = Episode(
        title=f"Integration Test Episode {datetime.now().strftime('%Y%m%d%H%M%S')}",
        file_hash=f"integration_test_hash_{datetime.now().timestamp()}",
        duration=300.0,
        source_url="https://test.com/integration-test",
        ai_summary="This is an integration test episode for NotionPublisher.",
        workflow_status=WorkflowStatus.PUBLISHED.value
    )
    integration_db.add(episode)
    integration_db.flush()

    # 创建 AudioSegment
    segment = AudioSegment(
        episode_id=episode.id,
        segment_index=0,
        segment_id="integration_segment_001",
        start_time=0.0,
        end_time=300.0,
        status="completed"
    )
    integration_db.add(segment)
    integration_db.flush()

    # 创建 Chapter
    chapter = Chapter(
        episode_id=episode.id,
        chapter_index=0,
        title="Integration Test Chapter",
        summary="This is a test chapter for integration testing.",
        start_time=0.0,
        end_time=300.0,
        status="completed"
    )
    integration_db.add(chapter)
    integration_db.flush()

    # 创建 TranscriptCue
    cues = []
    for i in range(5):
        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=i * 60.0,
            end_time=(i + 1) * 60.0,
            speaker="SPEAKER_00",
            text=f"This is integration test sentence {i + 1}."
        )
        cue.chapter_id = chapter.id
        cues.append(cue)
        integration_db.add(cue)
    integration_db.flush()

    # 创建 Translation
    for cue in cues:
        translation = Translation(
            cue_id=cue.id,
            language_code="zh",
            translation=f"这是集成测试句子 {cue.id}。",
            original_translation=f"这是集成测试句子 {cue.id}。",
            is_edited=False,
            translation_status=TranslationStatus.COMPLETED.value
        )
        integration_db.add(translation)
    integration_db.flush()

    return episode


# ========================================================================
# 集成测试
# ========================================================================

@requires_notion_config()
class TestNotionPublisherIntegration:
    """NotionPublisher 集成测试类"""

    def test_validate_config_with_real_api(self):
        """
        Given: 配置了有效的 NOTION_API_KEY
        When: 调用 validate_config
        Then: 返回 True
        """
        # Arrange
        publisher = NotionPublisher()

        # Act
        result = publisher.validate_config()

        # Assert
        assert result is True

    def test_publish_episode_to_real_notion(self, integration_episode, integration_db):
        """
        Given: Episode 和关联数据
        When: 调用 publish_episode
        Then: 成功发布到 Notion，返回成功状态
        """
        # Arrange
        publisher = NotionPublisher(db=integration_db)

        # Act
        result = publisher.publish_episode(integration_episode)

        # Assert
        assert result.status == "success"
        assert result.platform == "notion"
        assert result.platform_record_id is not None
        assert result.episode_id == integration_episode.id
        assert result.published_at is not None
        assert result.error_message is None

        print(f"\n发布成功！")
        print(f"  Episode ID: {integration_episode.id}")
        print(f"  Notion Page ID: {result.platform_record_id}")
        print(f"  Notion URL: https://notion.so/{result.platform_record_id.replace('-', '')}")

    def test_create_episode_page_with_real_api(self, integration_db):
        """
        Given: 有效的配置
        When: 创建测试页面
        Then: 成功创建并返回页面 ID
        """
        # Arrange
        publisher = NotionPublisher()
        test_title = f"Integration Test Page {datetime.now().strftime('%Y%m%d%H%M%S')}"

        # Act
        page_id = publisher.create_episode_page(
            title=test_title,
            parent_page_id=NOTION_PARENT_PAGE_ID
        )

        # Assert
        assert page_id is not None
        assert len(page_id) == 36  # UUID 格式

        print(f"\n测试页面创建成功！")
        print(f"  Page ID: {page_id}")
        print(f"  Notion URL: https://notion.so/{page_id.replace('-', '')}")

        # Cleanup - 归档测试页面
        try:
            publisher.client.pages.update(page_id=page_id, archived=True)
            print(f"  测试页面已归档")
        except Exception as e:
            print(f"  清理失败: {e}")

    def test_publish_episode_without_chapters(self, integration_db):
        """
        Given: Episode 没有 Chapter 数据
        When: 调用 publish_episode
        Then: 成功发布，不包含章节导航
        """
        # Arrange
        episode = Episode(
            title=f"No Chapter Test {datetime.now().strftime('%Y%m%d%H%M%S')}",
            file_hash=f"no_chapter_test_{datetime.now().timestamp()}",
            duration=60.0,
            source_url="https://test.com/no-chapter-test",
            ai_summary="Test episode without chapters.",
            workflow_status=WorkflowStatus.PUBLISHED.value
        )
        integration_db.add(episode)
        integration_db.flush()

        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=0,
            segment_id="no_chapter_segment",
            start_time=0.0,
            end_time=60.0,
            status="completed"
        )
        integration_db.add(segment)
        integration_db.flush()

        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=0.0,
            end_time=5.0,
            text="Hello world"
        )
        integration_db.add(cue)
        integration_db.flush()

        translation = Translation(
            cue_id=cue.id,
            language_code="zh",
            translation="你好世界",
            original_translation="你好世界",
            is_edited=False,
            translation_status=TranslationStatus.COMPLETED.value
        )
        integration_db.add(translation)
        integration_db.flush()

        publisher = NotionPublisher(db=integration_db)

        # Act
        result = publisher.publish_episode(episode)

        # Assert
        assert result.status == "success"

        # Cleanup - 归档测试页面
        try:
            publisher.client.pages.update(page_id=result.platform_record_id, archived=True)
        except Exception:
            pass


# ========================================================================
# 主运行入口
# ========================================================================

if __name__ == "__main__":
    """
    直接运行此脚本的快捷测试

    使用方法:
    1. 确保配置了 NOTION_API_KEY 和 NOTION_PARENT_PAGE_ID
    2. 运行: python -m pytest tests/integration/test_notion_publisher_integration.py -v -s
    """
    pytest.main([__file__, "-v", "-s"])
