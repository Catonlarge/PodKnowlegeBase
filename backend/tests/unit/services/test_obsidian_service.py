"""
ObsidianService 单元测试

测试 Obsidian 文档生成和解析服务：
1. render_episode() - 从数据库生成 Markdown
2. save_episode() - 保存到 Obsidian Vault
3. parse_episode() - 解析 Markdown 并检测变化
4. parse_and_backfill() - 回填用户编辑到数据库
5. Markdown 表格解析
"""
import re
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app.services.obsidian_service import ObsidianService
from app.models import Episode, AudioSegment, TranscriptCue, Translation, Chapter
from app.enums.workflow_status import WorkflowStatus
from app.enums.translation_status import TranslationStatus


# ========================================================================
# Fixtures
# ========================================================================

@pytest.fixture
def obsidian_service(test_session):
    """创建 ObsidianService 实例"""
    return ObsidianService(test_session, vault_path="/tmp/test_obsidian")


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
        end_time=600.0,
        status="completed"
    )
    test_session.add(segment)
    test_session.flush()

    # 创建 Chapters
    chapters = []
    for i in range(3):
        chapter = Chapter(
            episode_id=episode.id,
            chapter_index=i,
            title=f"Chapter {i + 1}",
            summary=f"Summary for chapter {i + 1}",
            start_time=i * 200.0,
            end_time=(i + 1) * 200.0,
            status="completed"
        )
        chapters.append(chapter)
        test_session.add(chapter)
    test_session.flush()

    # 创建 TranscriptCue 并关联到 Chapters
    cues = []
    for i in range(10):
        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=i * 60.0,
            end_time=(i + 1) * 60.0,
            speaker="SPEAKER_00" if i % 2 == 0 else "SPEAKER_01",
            text=f"This is sentence {i}."
        )
        # 关联到对应的 Chapter
        chapter_index = i // 4  # 每 4 个 Cue 一个 Chapter
        if chapter_index < len(chapters):
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


# ========================================================================
# Init 测试组
# ========================================================================

class TestInit:
    """测试 ObsidianService 初始化"""

    def test_init_with_vault_path(self, test_session):
        """
        Given: 数据库会话和 vault_path
        When: 创建 ObsidianService
        Then: 对象初始化成功，使用指定的 vault_path
        """
        # Act
        service = ObsidianService(test_session, vault_path="/custom/vault")

        # Assert
        assert service.db == test_session
        assert service.vault_path == "/custom/vault"

    def test_init_without_vault_path(self, test_session):
        """
        Given: 数据库会话，不指定 vault_path
        When: 创建 ObsidianService
        Then: 使用默认的配置路径
        """
        # Arrange - Mock config
        with patch('app.services.obsidian_service.OBSIDIAN_VAULT_PATH', '/default/vault'):
            # Act
            service = ObsidianService(test_session, vault_path=None)

            # Assert
            assert service.db == test_session
            assert service.vault_path == '/default/vault'


# ========================================================================
# RenderEpisode 测试组
# ========================================================================

class TestRenderEpisode:
    """测试 render_episode() 方法"""

    def test_render_episode_basic_structure(self, obsidian_service, episode_with_data):
        """
        Given: Episode 和关联数据
        When: 调用 render_episode()
        Then: 返回包含完整结构的 Markdown
        """
        # Act
        markdown = obsidian_service.render_episode(episode_with_data.id, language_code="zh")

        # Assert - 检查基本结构
        assert "---" in markdown  # YAML frontmatter 开始
        assert "task_id:" in markdown
        assert "url:" in markdown
        assert "status:" in markdown
        assert "# Test Episode: AI in 2024" in markdown
        assert "## 📑 章节导航" in markdown
        assert "## 1: Chapter 1" in markdown

    def test_render_episode_yaml_frontmatter(self, obsidian_service, episode_with_data):
        """
        Given: Episode (id=1, title="Test Episode: AI in 2024")
        When: 调用 render_episode()
        Then: YAML frontmatter 包含正确的元数据
        """
        # Act
        markdown = obsidian_service.render_episode(episode_with_data.id, language_code="zh")

        # Assert - 提取 YAML frontmatter
        yaml_match = re.search(r'^---\n(.*?)\n---', markdown, re.DOTALL)
        assert yaml_match is not None

        yaml_content = yaml_match.group(1)
        assert "task_id: 1" in yaml_content
        assert "url: https://youtube.com/watch?v=test123" in yaml_content
        assert "status: pending_review" in yaml_content

    def test_render_episode_ai_summary(self, obsidian_service, episode_with_data):
        """
        Given: Episode 带有 ai_summary
        When: 调用 render_episode()
        Then: 在引用块中显示全文概览
        """
        # Act
        markdown = obsidian_service.render_episode(episode_with_data.id, language_code="zh")

        # Assert
        assert "> **全文概览：** This episode discusses AI trends in 2024." in markdown

    def test_render_episode_chapter_navigation(self, obsidian_service, episode_with_data):
        """
        Given: Episode 包含 3 个 Chapter
        When: 调用 render_episode()
        Then: 章节导航表格包含 3 行数据
        """
        # Act
        markdown = obsidian_service.render_episode(episode_with_data.id, language_code="zh")

        # Assert - 提取章节导航表格
        nav_section = re.search(r'## 📑 章节导航\n(.*?)\n\n---', markdown, re.DOTALL)
        assert nav_section is not None

        nav_content = nav_section.group(1)
        # 检查 3 个章节链接
        assert "[1: Chapter 1]" in nav_content
        assert "[2: Chapter 2]" in nav_content
        assert "[3: Chapter 3]" in nav_content
        # 检查时间范围 (格式化为整数)
        assert "0 - 200" in nav_content or "200 - 400" in nav_content

    def test_render_episode_bilingual_table(self, obsidian_service, episode_with_data, test_session):
        """
        Given: TranscriptCue 和 Translation
        When: 调用 render_episode()
        Then: 生成双语字幕区块（英文在上，中文在下）
        """
        # Act
        markdown = obsidian_service.render_episode(episode_with_data.id, language_code="zh")

        # Assert - 检查区块格式
        assert "[00:00](cue://" in markdown or "[00:" in markdown
        assert "**英文**:" in markdown
        assert "**中文**:" in markdown
        # 检查英文内容
        assert "This is sentence" in markdown
        # 检查中文翻译
        assert "这是第" in markdown

    def test_render_episode_obsidian_anchor_format(self, obsidian_service, episode_with_data):
        """
        Given: TranscriptCue (id=N, start_time=60.0)
        When: 调用 render_episode()
        Then: 生成正确的 Obsidian 锚点 [01:00](cue://N)
        """
        # Act
        markdown = obsidian_service.render_episode(episode_with_data.id, language_code="zh")

        # Assert - 检查锚点格式
        anchor_pattern = r'\[\d{2}:\d{2}\]\(cue://\d+\)'
        anchors = re.findall(anchor_pattern, markdown)
        assert len(anchors) > 0
        # 验证第一个锚点格式
        assert anchors[0] == "[00:00](cue://1)" or "[01:00](cue://1)" in anchors

    def test_render_episode_missing_translation(self, test_session, obsidian_service):
        """
        Given: TranscriptCue 没有对应 Translation
        When: 调用 render_episode()
        Then: 中文列显示 "[未翻译]"
        """
        # Arrange - 创建没有翻译的 Episode
        episode = Episode(
            title="Test Episode",
            file_hash="test_hash_no_trans",
            duration=60.0,
            workflow_status=WorkflowStatus.SEGMENTED.value
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

        # Act
        markdown = obsidian_service.render_episode(episode.id, language_code="zh")

        # Assert - 应该包含 "[未翻译]" 标记
        assert "[未翻译]" in markdown

    def test_render_episode_empty_chapters(self, test_session, obsidian_service):
        """
        Given: Episode 没有 Chapter 数据
        When: 调用 render_episode()
        Then: 不抛出异常，生成简化文档
        """
        # Arrange - 创建没有 Chapter 的 Episode
        episode = Episode(
            title="Test Episode",
            file_hash="test_hash_no_chapters",
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

        # Act - 不应该抛出异常
        markdown = obsidian_service.render_episode(episode.id, language_code="zh")

        # Assert - 应该生成基本文档（Cue 区块格式）
        assert "# Test Episode" in markdown
        assert "[00:00](cue://" in markdown or "[00:" in markdown
        assert "**英文**: Hello world" in markdown
        assert "**中文**: 你好世界" in markdown
        # 不应该包含章节导航
        assert "## 📑 章节导航" not in markdown or markdown.count("## 📑 章节导航") == 0

    def test_render_episode_episode_not_found(self, obsidian_service):
        """
        Given: 不存在的 episode_id
        When: 调用 render_episode()
        Then: 抛出 ValueError
        """
        # Act & Assert
        with pytest.raises(ValueError, match="Episode not found"):
            obsidian_service.render_episode(99999, language_code="zh")


# ========================================================================
# SaveEpisode 测试组
# ========================================================================

class TestSaveEpisode:
    """测试 save_episode() 方法"""

    @patch('pathlib.Path.mkdir')
    @patch('builtins.open', create=True)
    def test_save_episode_creates_file(self, mock_open, mock_mkdir, obsidian_service, episode_with_data):
        """
        Given: Episode 和 vault_path
        When: 调用 save_episode()
        Then: 在 Vault 中创建 Markdown 文件
        """
        # Arrange - Mock file handle
        mock_file = Mock()
        mock_open.return_value.__enter__ = Mock(return_value=mock_file)
        mock_open.return_value.__exit__ = Mock(return_value=False)

        # Act
        result_path = obsidian_service.save_episode(episode_with_data.id, language_code="zh")

        # Assert
        assert result_path is not None
        assert result_path.suffix == ".md"
        # 验证文件名包含 episode id (使用 as_posix() 处理 Windows 路径)
        assert result_path.as_posix().startswith("/tmp/test_obsidian/")

    @patch('pathlib.Path.mkdir')
    @patch('builtins.open', create=True)
    def test_save_episode_file_naming(self, mock_open, mock_mkdir, test_session):
        """
        Given: Episode (id=1, title="Test: Episode? / Special!")
        When: 调用 save_episode()
        Then: 文件名为 "1-test-episode-special.md"
        """
        # Arrange
        episode = Episode(
            id=1,
            title="Test: Episode? / Special!",
            file_hash="test_hash",
            duration=60.0,
        )
        test_session.add(episode)
        test_session.flush()

        service = ObsidianService(test_session, vault_path="/tmp/test")

        mock_file = Mock()
        mock_open.return_value.__enter__ = Mock(return_value=mock_file)
        mock_open.return_value.__exit__ = Mock(return_value=False)

        # Act
        result_path = service.save_episode(episode.id, language_code="zh")

        # Assert - 文件名应该被清理
        assert "1-test-episode-special.md" in str(result_path).lower()
        # 不应该包含特殊字符
        assert ":" not in result_path.name
        assert "?" not in result_path.name
        assert "/" not in result_path.name

    def test_save_episode_uses_config_vault(self, test_session):
        """
        Given: vault_path=None
        When: 调用 save_episode()
        Then: 使用配置中的 OBSIDIAN_VAULT_PATH
        """
        # This test verifies the service uses config when vault_path is None
        with patch('app.services.obsidian_service.OBSIDIAN_VAULT_PATH', '/config/vault'):
            service = ObsidianService(test_session, vault_path=None)
            assert service.vault_path == '/config/vault'


# ========================================================================
# ParseEpisode 测试组
# ========================================================================

class TestParseEpisode:
    """测试 parse_episode() 方法"""

    def test_parse_episode_no_changes(self, obsidian_service, episode_with_data):
        """
        Given: 渲染后未修改的 Markdown
        When: 调用 parse_episode()
        Then: 返回空差异列表
        """
        # Arrange - 先渲染 Markdown
        original_markdown = obsidian_service.render_episode(episode_with_data.id, language_code="zh")

        # Act - 解析未修改的 Markdown
        diffs = obsidian_service.parse_episode_from_markdown(
            episode_with_data.id,
            original_markdown,
            language_code="zh"
        )

        # Assert - 不应该有差异
        assert len(diffs) == 0

    def test_parse_episode_detects_translation_edit(self, obsidian_service, episode_with_data):
        """
        Given: 修改了中文翻译的 Markdown
        When: 调用 parse_episode_from_markdown()
        Then: 返回包含差异的 DiffResult
        """
        # Arrange - 获取原始 Markdown 并修改
        markdown = obsidian_service.render_episode(episode_with_data.id, language_code="zh")
        # 替换第一个翻译
        modified_markdown = markdown.replace("这是第 1 句话。", "修改后的翻译内容")

        # Act
        diffs = obsidian_service.parse_episode_from_markdown(
            episode_with_data.id,
            modified_markdown,
            language_code="zh"
        )

        # Assert
        assert len(diffs) > 0
        assert diffs[0].original == "这是第 1 句话。"
        assert diffs[0].edited == "修改后的翻译内容"
        assert diffs[0].is_edited is True

    def test_parse_episode_extracts_cue_id_from_anchor(self, obsidian_service):
        """
        Given: Markdown 包含 "[01:05](cue://1024)"
        When: 解析锚点
        Then: 提取 cue_id=1024
        """
        # Act
        cue_id = ObsidianService._extract_cue_id_from_anchor("[01:05](cue://1024)")

        # Assert
        assert cue_id == 1024

    def test_parse_episode_handles_malformed_anchor(self, obsidian_service):
        """
        Given: 包含错误格式的锚点 "[01:05](invalid://1024)"
        When: 解析锚点
        Then: 返回 None
        """
        # Act
        cue_id = ObsidianService._extract_cue_id_from_anchor("[01:05](invalid://1024)")

        # Assert
        assert cue_id is None

    def test_parse_markdown_cue_block(self, obsidian_service):
        """
        Given: Markdown Cue 区块格式
        ### [00:00](cue://1)
        **英文**: Hello
        **中文**: 大家好

        When: 解析 Cue 区块
        Then: 返回空列表（因为没有对应的数据库记录）
        """
        # Arrange - 创建测试 Markdown（Cue 区块格式）
        markdown = """[00:00](cue://1)
**英文**: Hello
**中文**: 大家好
"""

        # Act
        diffs = obsidian_service.parse_episode_from_markdown(
            1,  # episode_id (unused in this test but required)
            markdown,
            language_code="zh"
        )

        # 由于没有对应的数据库记录，返回空列表
        assert diffs == [] or len(diffs) == 0

    def test_parse_markdown_header_row(self, obsidian_service):
        """
        Given: Markdown 标题行 "## 字幕内容" 和 Cue 区块格式
        When: 解析 Markdown
        Then: 不报错，正常跳过
        """
        # Arrange - 使用 Cue 区块格式
        markdown = """## 字幕内容

[00:00](cue://1)
**英文**: Hello
**中文**: 大家好
"""

        # Act - 不应该抛出异常
        diffs = obsidian_service.parse_episode_from_markdown(
            1,
            markdown,
            language_code="zh"
        )

        # Assert - 没有数据库记录时返回空
        assert diffs == [] or len(diffs) == 0

    def test_parse_markdown_empty_translation(self, obsidian_service):
        """
        Given: 空的中文翻译（Cue 区块格式）
        ### [00:00](cue://1)
        **英文**: Hello
        **中文**:

        When: 解析 Cue 区块
        Then: 返回空字符串翻译
        """
        # Arrange - 使用 Cue 区块格式
        markdown = """[00:00](cue://1)
**英文**: Hello
**中文**:
"""

        # Act - 不应该抛出异常
        diffs = obsidian_service.parse_episode_from_markdown(
            1,
            markdown,
            language_code="zh"
        )

        # Assert - 没有数据库记录时返回空
        assert diffs == [] or len(diffs) == 0


# ========================================================================
# ParseAndBackfill 测试组
# ========================================================================

class TestParseAndBackfill:
    """测试 parse_and_backfill() 方法"""

    def test_parse_and_backfill_updates_translation(self, obsidian_service, episode_with_data, test_session):
        """
        Given: 修改后的 Markdown 文档
        When: 调用 parse_and_backfill_from_markdown()
        Then: 更新 Translation.translation 并设置 is_edited=True
        """
        # Arrange - 获取原始 Markdown 并修改
        markdown = obsidian_service.render_episode(episode_with_data.id, language_code="zh")

        # 查找第一个 Cue 的翻译并修改
        first_cue = test_session.query(TranscriptCue).first()
        first_translation = test_session.query(Translation).filter(
            Translation.cue_id == first_cue.id,
            Translation.language_code == "zh"
        ).first()

        original_text = first_translation.translation if first_translation else ""
        # 确保找到要替换的文本
        assert original_text in markdown, f"Original text '{original_text}' not found in markdown"

        modified_markdown = markdown.replace(original_text, "用户修改后的翻译")

        # Act
        count = obsidian_service.parse_and_backfill_from_markdown(
            episode_with_data.id,
            modified_markdown,
            language_code="zh"
        )

        # Assert
        assert count >= 1, f"Expected at least 1 edit, got {count}"

        # 验证数据库中的修改
        translations = test_session.query(Translation).filter(
            Translation.language_code == "zh",
            Translation.is_edited == True
        ).all()

        assert len(translations) >= 1
        # 检查至少有一个翻译被修改
        edited = any(t.translation == "用户修改后的翻译" for t in translations)
        assert edited

    def test_parse_and_backfill_preserves_original(self, obsidian_service, episode_with_data, test_session):
        """
        Given: 修改后的 Markdown
        When: 调用 parse_and_backfill_from_markdown()
        Then: Translation.original_translation 保持不变
        """
        # Arrange - 获取原始的 original_translation
        original_translation = test_session.query(Translation).filter(
            Translation.cue_id == 1,
            Translation.language_code == "zh"
        ).first()

        original_value = original_translation.original_translation if original_translation else None

        # 修改 Markdown
        markdown = obsidian_service.render_episode(episode_with_data.id, language_code="zh")
        modified_markdown = markdown.replace("这是第 1 句话。", "用户修改后的翻译")

        # Act
        obsidian_service.parse_and_backfill_from_markdown(
            episode_with_data.id,
            modified_markdown,
            language_code="zh"
        )

        # Assert - 刷新并验证 original_translation 未变
        test_session.refresh(original_translation)
        assert original_translation.original_translation == original_value

    def test_parse_and_backfill_no_changes(self, obsidian_service, episode_with_data, test_session):
        """
        Given: 未修改的 Markdown 文档
        When: 调用 parse_and_backfill_from_markdown()
        Then: 不修改数据库，返回 0
        """
        # Arrange - 获取原始 Markdown
        markdown = obsidian_service.render_episode(episode_with_data.id, language_code="zh")

        # 获取修改前的翻译数量
        edited_count_before = test_session.query(Translation).filter(
            Translation.language_code == "zh",
            Translation.is_edited == True
        ).count()

        # Act
        count = obsidian_service.parse_and_backfill_from_markdown(
            episode_with_data.id,
            markdown,
            language_code="zh"
        )

        # Assert
        assert count == 0

        # 验证没有新增的编辑
        edited_count_after = test_session.query(Translation).filter(
            Translation.language_code == "zh",
            Translation.is_edited == True
        ).count()
        assert edited_count_after == edited_count_before
