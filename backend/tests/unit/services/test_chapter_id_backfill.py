"""
Unit tests for ChapterIdBackfiller

Test Naming Convention (BDD):
- test_<behavior>_<expected_result>

遵循 TDD 原则：先写测试，再写实现
"""
import pytest
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional

from app.models import Episode, Chapter, TranscriptCue, AudioSegment
from app.enums.workflow_status import WorkflowStatus


@dataclass
class BackfillStats:
    """回填统计信息"""
    episode_id: int
    total_cues: int = 0
    assigned_cues: int = 0
    reassigned_cues: int = 0
    skipped_cues: int = 0
    out_of_range_cues: int = 0
    null_chapter_before: int = 0
    null_chapter_after: int = 0
    chapter_issues: List[str] = field(default_factory=list)


class TestBackfillStats:
    """测试 BackfillStats 数据类"""

    def test_backfill_stats_initialization(self):
        """
        Given: episode_id
        When: 创建 BackfillStats
        Then: 正确初始化所有字段
        """
        # Arrange & Act
        stats = BackfillStats(episode_id=19)

        # Assert
        assert stats.episode_id == 19
        assert stats.total_cues == 0
        assert stats.assigned_cues == 0
        assert stats.reassigned_cues == 0
        assert stats.skipped_cues == 0
        assert stats.out_of_range_cues == 0
        assert stats.null_chapter_before == 0
        assert stats.null_chapter_after == 0
        assert stats.chapter_issues == []

    def test_backfill_stats_with_issues(self):
        """
        Given: 有章节数据问题的列表
        When: 创建 BackfillStats 并添加问题
        Then: 问题列表被正确存储
        """
        # Arrange & Act
        stats = BackfillStats(
            episode_id=19,
            chapter_issues=["重叠: 0 和 1", "间隙: 1 和 2"]
        )

        # Assert
        assert len(stats.chapter_issues) == 2
        assert "重叠" in stats.chapter_issues[0]
        assert "间隙" in stats.chapter_issues[1]


class TestChapterIdBackfiller:
    """测试 ChapterIdBackfiller 核心功能"""

    @pytest.fixture
    def backfiller(self, test_session):
        """创建 ChapterIdBackfiller 实例"""
        from app.services.chapter_id_backfill import ChapterIdBackfiller
        return ChapterIdBackfiller(test_session)

    @pytest.fixture
    def episode_with_chapters_and_cues(self, test_session):
        """
        创建完整的测试数据：
        - 1个 Episode
        - 3个 Chapters（有时间范围）
        - 10个 TranscriptCues（通过 AudioSegment 关联）
        """
        # 创建 Episode
        episode = Episode(
            title="Test Episode",
            file_hash="test_hash_backfill",
            duration=900.0,
            workflow_status=WorkflowStatus.PUBLISHED.value
        )
        test_session.add(episode)
        test_session.flush()

        # 创建 AudioSegment
        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=0,
            segment_id="segment_backfill_001",
            start_time=0.0,
            end_time=900.0,
            status="completed"
        )
        test_session.add(segment)
        test_session.flush()

        # 创建 3 个 Chapters
        chapters = []
        for i in range(3):
            chapter = Chapter(
                episode_id=episode.id,
                chapter_index=i,
                title=f"Chapter {i + 1}",
                summary=f"Summary for chapter {i + 1}",
                start_time=i * 300.0,  # 0-300, 300-600, 600-900
                end_time=(i + 1) * 300.0,
                status="completed"
            )
            chapters.append(chapter)
            test_session.add(chapter)
        test_session.flush()

        # 创建 10 个 TranscriptCues
        cues = []
        for i in range(10):
            cue = TranscriptCue(
                segment_id=segment.id,
                start_time=i * 90.0,  # 每90秒一个cue
                end_time=(i + 1) * 90.0,
                speaker="SPEAKER_00" if i % 2 == 0 else "SPEAKER_01",
                text=f"This is sentence {i}."
            )
            # 前3个cues设置chapter_id（模拟已有数据）
            if i < 3:
                cue.chapter_id = chapters[0].id
            # 中间3个cues设置错误的chapter_id（模拟需要重新分配）
            elif i < 6:
                cue.chapter_id = chapters[1].id
            # 最后4个cues不设置chapter_id（模拟NULL）
            cues.append(cue)
            test_session.add(cue)
        test_session.flush()

        return {
            "episode": episode,
            "chapters": chapters,
            "cues": cues
        }

    def test_validate_chapters_with_valid_data(self, backfiller):
        """
        Given: 有效的章节数据（无重叠、无间隙）
        When: 调用 _validate_chapters
        Then: 返回空列表（无问题）
        """
        # Arrange
        from app.models import Chapter
        chapters = [
            Chapter(
                episode_id=1,
                chapter_index=0,
                title="Chapter 1",
                start_time=0.0,
                end_time=300.0,
                status="completed"
            ),
            Chapter(
                episode_id=1,
                chapter_index=1,
                title="Chapter 2",
                start_time=300.0,
                end_time=600.0,
                status="completed"
            )
        ]

        # Act
        issues = backfiller._validate_chapters(chapters)

        # Assert
        assert issues == []

    def test_validate_chapters_detects_overlap(self, backfiller):
        """
        Given: 有重叠的章节数据
        When: 调用 _validate_chapters
        Then: 返回重叠问题列表
        """
        # Arrange
        from app.models import Chapter
        chapters = [
            Chapter(
                episode_id=1,
                chapter_index=0,
                title="Chapter 1",
                start_time=0.0,
                end_time=350.0,  # 重叠到下一个章节
                status="completed"
            ),
            Chapter(
                episode_id=1,
                chapter_index=1,
                title="Chapter 2",
                start_time=300.0,
                end_time=600.0,
                status="completed"
            )
        ]

        # Act
        issues = backfiller._validate_chapters(chapters)

        # Assert
        assert len(issues) == 1
        assert "重叠" in issues[0]

    def test_validate_chapters_detects_gap(self, backfiller):
        """
        Given: 有间隙的章节数据
        When: 调用 _validate_chapters
        Then: 返回间隙问题列表
        """
        # Arrange
        from app.models import Chapter
        chapters = [
            Chapter(
                episode_id=1,
                chapter_index=0,
                title="Chapter 1",
                start_time=0.0,
                end_time=300.0,
                status="completed"
            ),
            Chapter(
                episode_id=1,
                chapter_index=1,
                title="Chapter 2",
                start_time=400.0,  # 有100秒间隙
                end_time=600.0,
                status="completed"
            )
        ]

        # Act
        issues = backfiller._validate_chapters(chapters)

        # Assert
        assert len(issues) == 1
        assert "间隙" in issues[0]

    def test_validate_chapters_detects_reverse_order(self, backfiller):
        """
        Given: 顺序错误的章节数据
        When: 调用 _validate_chapters
        Then: 返回倒序问题列表
        """
        # Arrange
        from app.models import Chapter
        chapters = [
            Chapter(
                episode_id=1,
                chapter_index=1,
                title="Chapter 2",
                start_time=300.0,
                end_time=600.0,
                status="completed"
            ),
            Chapter(
                episode_id=1,
                chapter_index=0,
                title="Chapter 1",
                start_time=0.0,  # 完全在前面，只测试顺序错误
                end_time=300.0,
                status="completed"
            )
        ]

        # Act
        issues = backfiller._validate_chapters(chapters)

        # Assert - 应该检测到重叠（因为chapters[0].end_time=600 > chapters[1].start_time=0）
        # 和顺序错误（chapters[0].start_time=300 > chapters[1].start_time=0）
        assert len(issues) == 2
        assert any("顺序错误" in issue for issue in issues)

    def test_assign_cue_to_chapter_normal_case(self, backfiller, episode_with_chapters_and_cues):
        """
        Given: Cue 时间在 Chapter 范围内
        When: 调用 _assign_cue_to_chapter
        Then: 返回正确的 Chapter
        """
        # Arrange
        data = episode_with_chapters_and_cues
        chapters = data["chapters"]
        cue = data["cues"][0]  # start_time = 0, 应该分配到 Chapter 0

        # Act
        result = backfiller._assign_cue_to_chapter(cue, chapters)

        # Assert
        assert result is not None
        assert result.chapter_index == 0
        assert result.id == chapters[0].id

    def test_assign_cue_to_chapter_boundary_case(self, backfiller, episode_with_chapters_and_cues):
        """
        Given: Cue 时间正好在章节边界
        When: 调用 _assign_cue_to_chapter
        Then: 分配给正确的 Chapter（使用左闭右开区间）
        """
        # Arrange
        data = episode_with_chapters_and_cues
        chapters = data["chapters"]

        # 创建一个边界 cue (start_time = 300, 应该分配到 Chapter 1)
        boundary_cue = TranscriptCue(
            segment_id=data["cues"][0].segment_id,
            start_time=300.0,  # 正好在 Chapter 1 的开始时间
            end_time=390.0,
            speaker="SPEAKER_00",
            text="Boundary cue"
        )

        # Act
        result = backfiller._assign_cue_to_chapter(boundary_cue, chapters)

        # Assert
        assert result is not None
        assert result.chapter_index == 1
        assert result.start_time == 300.0
        assert result.end_time == 600.0

    def test_assign_cue_to_chapter_out_of_range(self, backfiller, episode_with_chapters_and_cues):
        """
        Given: Cue 时间超出所有 Chapter 范围
        When: 调用 _assign_cue_to_chapter
        Then: 返回 None（由调用方处理范围外情况）
        """
        # Arrange
        data = episode_with_chapters_and_cues
        chapters = data["chapters"]

        # 创建一个超出范围的 cue (最后一个chapter结束时间是900)
        out_of_range_cue = TranscriptCue(
            segment_id=data["cues"][0].segment_id,
            start_time=950.0,  # 超出最后一个chapter (900)
            end_time=990.0,
            speaker="SPEAKER_00",
            text="Out of range cue"
        )

        # Act
        result = backfiller._assign_cue_to_chapter(out_of_range_cue, chapters)

        # Assert - 返回 None，由 backfill_episode 处理
        assert result is None

    def test_assign_cue_to_chapter_no_chapters(self, backfiller, test_session):
        """
        Given: 空的 Chapters 列表
        When: 调用 _assign_cue_to_chapter
        Then: 返回 None
        """
        # Arrange
        episode = Episode(
            title="Test Episode",
            file_hash="test_hash",
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
            start_time=30.0,
            end_time=35.0,
            speaker="SPEAKER_00",
            text="Test cue"
        )
        test_session.add(cue)
        test_session.flush()

        # Act
        result = backfiller._assign_cue_to_chapter(cue, [])

        # Assert
        assert result is None

    def test_assign_cue_to_chapter_with_overlap(self, backfiller):
        """
        Given: Chapter 有重叠，Cue 在重叠区域内
        When: 调用 _assign_cue_to_chapter
        Then: 分配给第一个匹配的 Chapter（chapter_index 最小）
        """
        # Arrange
        from app.models import Chapter
        chapters = [
            Chapter(
                episode_id=1,
                chapter_index=0,
                title="Chapter 1",
                start_time=0.0,
                end_time=350.0,  # 重叠到下一个章节
                status="completed"
            ),
            Chapter(
                episode_id=1,
                chapter_index=1,
                title="Chapter 2",
                start_time=300.0,
                end_time=600.0,
                status="completed"
            )
        ]

        # 创建一个在重叠区域的 cue (320s 应该分配给 Chapter 0)
        cue = TranscriptCue(
            segment_id=1,
            start_time=320.0,
            end_time=330.0,
            speaker="SPEAKER_00",
            text="Overlap cue"
        )

        # Act
        result = backfiller._assign_cue_to_chapter(cue, chapters)

        # Assert
        assert result is not None
        assert result.chapter_index == 0  # 第一个匹配的章节
        assert result.start_time == 0.0
        assert result.end_time == 350.0

    def test_backfill_episode_with_null_chapter_ids(self, backfiller, episode_with_chapters_and_cues):
        """
        Given: Episode 有 NULL chapter_id 的 Cues
        When: 调用 backfill_episode (dry_run=True)
        Then: 正确分配 chapter_id 并返回统计信息
        """
        # Arrange
        data = episode_with_chapters_and_cues

        # 设置后4个cues的chapter_id为NULL
        for i in range(6, 10):
            data["cues"][i].chapter_id = None

        # Act
        stats = backfiller.backfill_episode(data["episode"].id, dry_run=True)

        # Assert
        assert stats.episode_id == data["episode"].id
        assert stats.total_cues == 10
        assert stats.null_chapter_before == 4  # 前4个有chapter_id，后4个为NULL
        assert stats.null_chapter_after == 0  # 全部被分配
        assert stats.assigned_cues + stats.skipped_cues == 10

    def test_backfill_episode_with_correct_chapters_skipped(self, backfiller, episode_with_chapters_and_cues):
        """
        Given: Episode 的 Cues chapter_id 已经正确
        When: 调用 backfill_episode
        Then: 跳过已正确分配的 Cues
        """
        # Arrange
        data = episode_with_chapters_and_cues

        # 所有cues的chapter_id都已经正确设置
        # cue 0-2 在 chapter 0, cue 3-5 在 chapter 1, cue 6-9 需要计算

        # Act
        stats = backfiller.backfill_episode(data["episode"].id, dry_run=True)

        # Assert
        assert stats.episode_id == data["episode"].id
        assert stats.total_cues == 10
        # 前6个cue的chapter_id已经正确，应该被跳过
        assert stats.skipped_cues == 6
        # 后4个cue的chapter_id需要被分配
        assert stats.assigned_cues == 4

    def test_backfill_episode_with_force_reassign(self, backfiller, episode_with_chapters_and_cues):
        """
        Given: Episode 的 Cues 有错误的 chapter_id
        When: 调用 backfill_episode (force=True)
        Then: 重新分配错误的 chapter_id
        """
        # Arrange
        data = episode_with_chapters_and_cues

        # 故意设置错误的chapter_id：cue 0 应该在 chapter 0，但设置为 chapter 1
        data["cues"][0].chapter_id = data["chapters"][1].id

        # Act
        stats = backfiller.backfill_episode(
            data["episode"].id,
            dry_run=True,
            force=True  # 强制重新分配
        )

        # Assert
        assert stats.episode_id == data["episode"].id
        assert stats.reassigned_cues >= 1  # 至少cue 0 被重新分配

    def test_backfill_episode_dry_run_mode(self, backfiller, test_session):
        """
        Given: Episode 和 Chapters
        When: 调用 backfill_episode (dry_run=True)
        Then: 执行所有逻辑并返回统计信息，但不提交更改
        """
        # Arrange
        episode = Episode(
            title="Dry Run Test",
            file_hash="dry_run_test",
            duration=300.0,
            workflow_status=WorkflowStatus.PUBLISHED.value
        )
        test_session.add(episode)
        test_session.flush()

        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=0,
            segment_id="segment_dry_run",
            start_time=0.0,
            end_time=300.0,
            status="completed"
        )
        test_session.add(segment)
        test_session.flush()

        chapter = Chapter(
            episode_id=episode.id,
            chapter_index=0,
            title="Chapter 1",
            start_time=0.0,
            end_time=300.0,
            status="completed"
        )
        test_session.add(chapter)
        test_session.flush()

        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=100.0,
            end_time=150.0,
            speaker="SPEAKER_00",
            text="Dry run test cue"
        )
        test_session.add(cue)
        test_session.flush()

        # Act - dry_run=True 执行逻辑但不提交
        stats = backfiller.backfill_episode(episode.id, dry_run=True)

        # Assert - 验证逻辑正确执行（统计信息正确）
        assert stats.total_cues == 1
        assert stats.assigned_cues == 1
        assert stats.null_chapter_before == 1  # 原始没有chapter_id
        # 注意：由于 dry_run=True，实际的 cue.chapter_id 不会改变（会回滚）


class TestBackfillEpisodeIntegration:
    """集成测试：完整的回填流程"""

    def test_backfill_episode_comprehensive_workflow(self, test_session):
        """
        Given: 完整的 Episode 数据（Episode + Chapters + Cues）
        When: 执行完整的 backfill_episode 流程
        Then: 正确分配所有 cues 的 chapter_id
        """
        # Arrange
        episode = Episode(
            title="Integration Test",
            file_hash="integration_test",
            duration=900.0,
            workflow_status=WorkflowStatus.PUBLISHED.value
        )
        test_session.add(episode)
        test_session.flush()

        segment = AudioSegment(
            episode_id=episode.id,
            segment_index=0,
            segment_id="segment_integration",
            start_time=0.0,
            end_time=900.0,
            status="completed"
        )
        test_session.add(segment)
        test_session.flush()

        # 创建 3 个 chapters
        chapters = []
        for i in range(3):
            chapter = Chapter(
                episode_id=episode.id,
                chapter_index=i,
                title=f"Chapter {i + 1}",
                summary=f"Summary {i + 1}",
                start_time=i * 300.0,
                end_time=(i + 1) * 300.0,
                status="completed"
            )
            chapters.append(chapter)
            test_session.add(chapter)
        test_session.flush()

        # 创建 15 个 cues，分布在不同的章节
        cues = []
        for i in range(15):
            cue = TranscriptCue(
                segment_id=segment.id,
                start_time=i * 60.0,  # 每60秒一个cue
                end_time=(i + 1) * 60.0,
                speaker="SPEAKER_00",
                text=f"Integration test cue {i}"
            )
            cues.append(cue)
            test_session.add(cue)
        test_session.flush()

        # Act
        from app.services.chapter_id_backfill import ChapterIdBackfiller
        backfiller = ChapterIdBackfiller(test_session)
        stats = backfiller.backfill_episode(episode.id, dry_run=False)

        # Assert
        assert stats.episode_id == episode.id
        assert stats.total_cues == 15
        assert stats.assigned_cues == 15  # 所有15个cues都应该被新分配
        assert stats.null_chapter_after == 0  # 回填后没有NULL

        # 验证每个 cue 被分配到正确的 chapter
        for i, cue in enumerate(cues):
            expected_chapter_index = i // 5  # 每5个cue一个章节（0-4→ch0, 5-9→ch1, 10-14→ch2）
            expected_chapter_id = chapters[expected_chapter_index].id

            assert cue.chapter_id == expected_chapter_id, \
                f"Cue {i} (start_time={cue.start_time}) should be in chapter {expected_chapter_index}"
