"""
ObsidianService 集成测试

测试完整的渲染-保存-解析-回填流程
"""
import re
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app.services.obsidian_service import ObsidianService
from app.models import Episode, AudioSegment, TranscriptCue, Translation, Chapter
from app.enums.workflow_status import WorkflowStatus
from app.enums.translation_status import TranslationStatus


@pytest.fixture
def full_episode_data(test_session):
    """创建完整的 Episode 数据用于集成测试"""
    # 创建 Episode
    episode = Episode(
        title="Integration Test Episode",
        file_hash="integration_test_hash",
        duration=300.0,
        source_url="https://youtube.com/watch?v=integration_test",
        ai_summary="This is an integration test episode.",
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
            text=f"This is test sentence {i}."
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
            translation=f"这是测试句子 {cue.id}。",
            original_translation=f"这是测试句子 {cue.id}。",
            is_edited=False,
            translation_status=TranslationStatus.COMPLETED.value
        )
        test_session.add(translation)
    test_session.flush()

    return episode


class TestObsidianIntegration:
    """ObsidianService 集成测试"""

    def test_full_render_save_parse_cycle(self, full_episode_data, test_session):
        """
        Given: 完整的 Episode 数据
        When:
            1. 调用 render_episode() 生成 Markdown
            2. 修改 Markdown 中的翻译
            3. 调用 parse_and_backfill_from_markdown() 回填
        Then:
            1. Markdown 正确生成
            2. 修改被正确检测和回填
            3. is_edited 标志正确设置
        """
        # Arrange
        service = ObsidianService(test_session, vault_path="/tmp/test_vault")
        episode_id = full_episode_data.id

        # Act 1: 渲染 Markdown
        markdown = service.render_episode(episode_id, language_code="zh")

        # Assert 1: 验证 Markdown 结构
        assert "---" in markdown
        assert "task_id:" in markdown
        assert "# Integration Test Episode" in markdown
        assert "## 📑 章节导航" in markdown
        assert "## 1: Chapter 1" in markdown
        assert "## 2: Chapter 2" in markdown
        # Cue 区块格式
        assert "[00:00](cue://" in markdown or "[00:" in markdown
        assert "**英文**:" in markdown
        assert "**中文**:" in markdown

        # Act 2: 修改翻译（修改第一个 Cue 的翻译）
        first_cue = test_session.query(TranscriptCue).first()
        first_translation = test_session.query(Translation).filter(
            Translation.cue_id == first_cue.id,
            Translation.language_code == "zh"
        ).first()

        original_text = first_translation.translation
        modified_text = "用户手动修改后的翻译内容"

        modified_markdown = markdown.replace(original_text, modified_text)

        # Assert 2: 验证替换成功
        assert modified_text in modified_markdown
        assert original_text not in modified_markdown

        # Act 3: 回填修改
        count = service.parse_and_backfill_from_markdown(
            episode_id,
            modified_markdown,
            language_code="zh"
        )

        # Assert 3: 验证回填结果
        assert count == 1

        # 刷新数据库对象
        test_session.refresh(first_translation)

        # 验证 translation 字段被更新
        assert first_translation.translation == modified_text
        # 验证 original_translation 保持不变
        assert first_translation.original_translation == original_text
        # 验证 is_edited 标志被设置
        assert first_translation.is_edited is True

    def test_render_with_all_features(self, full_episode_data, test_session):
        """
        Given: 完整的 Episode 数据
        When: 调用 render_episode()
        Then: 生成的 Markdown 包含所有预期功能
        """
        # Arrange
        service = ObsidianService(test_session, vault_path="/tmp/test_vault")

        # Act
        markdown = service.render_episode(full_episode_data.id, language_code="zh")

        # Assert - YAML Frontmatter
        yaml_match = re.search(r'^---\n(.*?)\n---', markdown, re.DOTALL)
        assert yaml_match is not None
        yaml_content = yaml_match.group(1)
        assert f"task_id: {full_episode_data.id}" in yaml_content
        assert f"url: {full_episode_data.source_url}" in yaml_content
        assert "status: pending_review" in yaml_content

        # Assert - 标题和概览
        assert f"# {full_episode_data.title}" in markdown
        assert f"> **全文概览：** {full_episode_data.ai_summary}" in markdown

        # Assert - 章节导航
        assert "## 📑 章节导航" in markdown
        assert "[1: Chapter 1]" in markdown
        assert "[2: Chapter 2]" in markdown

        # Assert - 章节内容
        assert "## 1: Chapter 1" in markdown
        assert "## 2: Chapter 2" in markdown
        assert "> **章节摘要：** Summary for chapter" in markdown

        # Assert - 双语字幕区块（Cue 区块格式）
        assert "[00:00](cue://" in markdown or "[00:" in markdown
        assert "**英文**:" in markdown
        assert "**中文**:" in markdown
        # 验证锚点格式
        anchor_pattern = r'\[\d{2}:\d{2}\]\(cue://\d+\)'
        anchors = re.findall(anchor_pattern, markdown)
        assert len(anchors) == 6  # 6 个 Cue

    def test_multiple_edits_detected(self, full_episode_data, test_session):
        """
        Given: 完整的 Episode 数据
        When: 修改多个翻译并解析
        Then: 所有修改都被正确检测
        """
        # Arrange
        service = ObsidianService(test_session, vault_path="/tmp/test_vault")

        # 渲染 Markdown
        markdown = service.render_episode(full_episode_data.id, language_code="zh")

        # 修改前 3 个 Cue 的翻译
        cues = test_session.query(TranscriptCue).limit(3).all()
        modifications = {}
        for cue in cues:
            translation = test_session.query(Translation).filter(
                Translation.cue_id == cue.id,
                Translation.language_code == "zh"
            ).first()
            if translation:
                modifications[cue.id] = f"修改后的翻译 {cue.id}"
                markdown = markdown.replace(translation.translation, modifications[cue.id])

        # Act
        diffs = service.parse_episode_from_markdown(
            full_episode_data.id,
            markdown,
            language_code="zh"
        )

        # Assert
        assert len(diffs) == 3
        # 验证每个差异
        for diff in diffs:
            assert diff.cue_id in modifications
            assert diff.edited == modifications[diff.cue_id]
            assert diff.is_edited is True

    def test_no_changes_when_markdown_unchanged(self, full_episode_data, test_session):
        """
        Given: 完整的 Episode 数据
        When: 解析未修改的 Markdown
        Then: 不检测到任何差异
        """
        # Arrange
        service = ObsidianService(test_session, vault_path="/tmp/test_vault")

        # 渲染 Markdown
        markdown = service.render_episode(full_episode_data.id, language_code="zh")

        # Act - 解析未修改的 Markdown
        diffs = service.parse_episode_from_markdown(
            full_episode_data.id,
            markdown,
            language_code="zh"
        )

        # Assert - 不应该有差异
        assert len(diffs) == 0

    @patch('pathlib.Path.mkdir')
    @patch('builtins.open', create=True)
    def test_save_episode_creates_correct_file(self, mock_open_func, mock_mkdir, full_episode_data, test_session):
        """
        Given: Episode 数据
        When: 调用 save_episode()
        Then: 创建正确路径和名称的文件
        """
        # Arrange - Mock file operations
        mock_file = Mock()
        mock_open_func.return_value.__enter__ = Mock(return_value=mock_file)
        mock_open_func.return_value.__exit__ = Mock(return_value=False)

        service = ObsidianService(test_session, vault_path="/tmp/test_vault")

        # Act
        file_path = service.save_episode(full_episode_data.id, language_code="zh")

        # Assert
        assert file_path.name == f"{full_episode_data.id}-integration-test-episode.md"
        assert file_path.parent.name.lower() == "episodes"

        # 验证文件被写入
        mock_file.write.assert_called_once()
        written_content = mock_file.write.call_args[0][0]
        assert "# Integration Test Episode" in written_content

    def test_obsidian_anchor_property_works(self, full_episode_data, test_session):
        """
        Given: TranscriptCue 对象
        When: 访问 obsidian_anchor 属性
        Then: 返回正确的 Markdown 链接
        """
        # Arrange
        cue = test_session.query(TranscriptCue).first()

        # Act
        anchor = cue.obsidian_anchor

        # Assert
        assert "[00:00](cue://" in anchor or "[00:" in anchor
        assert str(cue.id) in anchor
        assert anchor.endswith(")")

    def test_episode_without_chapters(self, test_session):
        """
        Given: 没有 Chapter 的 Episode
        When: 调用 render_episode()
        Then: 生成简化文档，不包含章节导航
        """
        # Arrange - 创建没有 Chapter 的 Episode
        episode = Episode(
            title="No Chapters Episode",
            file_hash="no_chapters_hash",
            duration=60.0,
            workflow_status=WorkflowStatus.TRANSLATED.value
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

        service = ObsidianService(test_session, vault_path="/tmp/test_vault")

        # Act
        markdown = service.render_episode(episode.id, language_code="zh")

        # Assert - Cue 区块格式
        assert "# No Chapters Episode" in markdown
        assert "[00:00](cue://" in markdown or "[00:" in markdown
        assert "**英文**: Hello world" in markdown
        assert "**中文**: 你好世界" in markdown
        # 应该有字幕内容部分，但没有章节导航
        assert "## 字幕内容" in markdown or markdown.count("##") == 1  # 只有标题
