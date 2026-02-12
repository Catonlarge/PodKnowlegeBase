"""
Chapter ID Backfill Service

回填 TranscriptCue.chapter_id 字段，根据时间范围将 cues 分配到对应的 chapters。

核心算法：
1. 一次性获取所有 cues（性能优化）
2. 按章节时间范围匹配（左闭右开区间 [start, end)）
3. 处理边界情况（重叠、间隙、范围外）
4. 支持 dry-run 模式和 force 重新分配
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models import Episode, Chapter, TranscriptCue, AudioSegment

logger = logging.getLogger(__name__)


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

    def __str__(self) -> str:
        """格式化输出统计信息"""
        return (
            f"Episode {self.episode_id} 回填统计:\n"
            f"  总 cues 数: {self.total_cues}\n"
            f"  新分配: {self.assigned_cues}\n"
            f"  重新分配: {self.reassigned_cues}\n"
            f"  跳过: {self.skipped_cues}\n"
            f"  范围外: {self.out_of_range_cues}\n"
            f"  回填前 NULL: {self.null_chapter_before}\n"
            f"  回填后 NULL: {self.null_chapter_after}"
        )


class ChapterIdBackfiller:
    """
    Chapter ID 回填服务

    负责：
    1. 根据时间范围回填 chapter_id 到 cues
    2. 验证章节数据完整性
    3. 提供详细的统计信息

    Attributes:
        db: 数据库会话
    """

    def __init__(self, db: Session):
        """
        初始化 ChapterIdBackfiller

        Args:
            db: 数据库会话
        """
        self.db = db

    # ========================================================================
    # 核心回填方法
    # ========================================================================

    def backfill_episode(
        self,
        episode_id: int,
        dry_run: bool = False,
        force: bool = False
    ) -> BackfillStats:
        """
        回填单个 episode 的 chapter_id

        Args:
            episode_id: Episode ID
            dry_run: 是否为干运行模式（不提交更改）
            force: 是否强制重新分配（纠正错误的chapter_id）

        Returns:
            BackfillStats: 回填统计信息
        """
        logger.info(f"开始回填 episode {episode_id} (dry_run={dry_run}, force={force})")

        # 初始化统计信息
        stats = BackfillStats(episode_id=episode_id)

        # 1. 获取所有 chapters（按时间排序）
        chapters = self.db.query(Chapter).filter(
            Chapter.episode_id == episode_id
        ).order_by(Chapter.start_time).all()

        if not chapters:
            logger.warning(f"Episode {episode_id} 没有章节，跳过")
            return stats

        # 2. 验证章节数据
        stats.chapter_issues = self._validate_chapters(chapters)
        if stats.chapter_issues:
            logger.warning(f"Episode {episode_id} 章节数据存在问题: {stats.chapter_issues}")

        # 3. 一次性获取该 episode 的所有 cues（通过 AudioSegment 关联）
        all_cues = self.db.query(TranscriptCue).join(
            AudioSegment, TranscriptCue.segment_id == AudioSegment.id
        ).filter(
            AudioSegment.episode_id == episode_id
        ).order_by(TranscriptCue.start_time).all()

        if not all_cues:
            logger.warning(f"Episode {episode_id} 没有字幕 cues，跳过")
            return stats

        stats.total_cues = len(all_cues)
        stats.null_chapter_before = sum(1 for cue in all_cues if cue.chapter_id is None)

        # 4. 为每个 cue 分配 chapter
        for cue in all_cues:
            # 判断是否需要分配
            needs_assignment = cue.chapter_id is None or force

            if not needs_assignment:
                # 验证现有的 chapter_id 是否正确
                current_chapter = self._assign_cue_to_chapter(cue, chapters)
                if current_chapter and cue.chapter_id == current_chapter.id:
                    stats.skipped_cues += 1
                    continue
                # 如果现有 chapter_id 错误且 force=False，跳过
                elif not force:
                    stats.skipped_cues += 1
                    continue

            # 执行分配
            target_chapter = self._assign_cue_to_chapter(cue, chapters)

            if target_chapter is None:
                # 没有找到匹配的 chapter，分配给最后一个
                if chapters:
                    target_chapter = chapters[-1]
                    stats.out_of_range_cues += 1
                else:
                    # 不应该发生，因为前面已经检查过
                    continue

            # 更新 chapter_id
            old_chapter_id = cue.chapter_id
            cue.chapter_id = target_chapter.id

            # 统计
            if old_chapter_id is None:
                stats.assigned_cues += 1
            elif old_chapter_id != target_chapter.id:
                stats.reassigned_cues += 1

        # 5. 提交或回滚
        stats.null_chapter_after = sum(1 for cue in all_cues if cue.chapter_id is None)

        if not dry_run:
            self.db.commit()
            logger.info(f"Episode {episode_id} 回填完成: {stats}")
        else:
            self.db.rollback()
            logger.info(f"Episode {episode_id} 干运行完成: {stats}")

        return stats

    def backfill_all_episodes(
        self,
        limit: Optional[int] = None,
        episode_ids: Optional[List[int]] = None,
        dry_run: bool = False,
        force: bool = False
    ) -> List[BackfillStats]:
        """
        回填多个 episodes 的 chapter_id

        Args:
            limit: 限制处理的 episode 数量（用于测试）
            episode_ids: 指定要处理的 episode ID 列表
            dry_run: 是否为干运行模式
            force: 是否强制重新分配

        Returns:
            List[BackfillStats]: 每个 episode 的回填统计信息
        """
        logger.info(f"开始批量回填 (limit={limit}, episode_ids={episode_ids}, dry_run={dry_run}, force={force})")

        # 获取目标 episodes
        if episode_ids:
            episodes = self.db.query(Episode).filter(
                Episode.id.in_(episode_ids)
            ).order_by(Episode.id).all()
        else:
            query = self.db.query(Episode).order_by(Episode.id)
            if limit:
                query = query.limit(limit)
            episodes = query.all()

        logger.info(f"找到 {len(episodes)} 个 episodes 需要处理")

        # 逐个处理
        all_stats = []
        for episode in episodes:
            try:
                stats = self.backfill_episode(episode.id, dry_run=dry_run, force=force)
                all_stats.append(stats)
            except Exception as e:
                logger.error(f"处理 episode {episode.id} 时出错: {e}")
                # 创建失败统计
                error_stats = BackfillStats(
                    episode_id=episode.id,
                    chapter_issues=[f"处理失败: {str(e)}"]
                )
                all_stats.append(error_stats)

        # 输出总体统计
        total_assigned = sum(s.assigned_cues for s in all_stats)
        total_reassigned = sum(s.reassigned_cues for s in all_stats)
        total_skipped = sum(s.skipped_cues for s in all_stats)
        logger.info(
            f"批量回填完成: 总分配={total_assigned}, 总重新分配={total_reassigned}, 总跳过={total_skipped}"
        )

        return all_stats

    # ========================================================================
    # 私有辅助方法
    # ========================================================================

    def _validate_chapters(self, chapters: List[Chapter]) -> List[str]:
        """
        验证章节数据，返回问题列表

        检查项：
        1. 章节重叠
        2. 章节间隙
        3. 章节顺序错误

        Args:
            chapters: Chapter 列表

        Returns:
            List[str]: 问题描述列表
        """
        issues = []

        for i in range(len(chapters) - 1):
            current = chapters[i]
            next_chap = chapters[i + 1]

            # 检查重叠
            if current.end_time > next_chap.start_time:
                issues.append(
                    f"章节重叠: {current.chapter_index} ({current.start_time}-{current.end_time}) "
                    f"与 {next_chap.chapter_index} ({next_chap.start_time}-{next_chap.end_time})"
                )

            # 检查间隙
            if current.end_time < next_chap.start_time:
                gap = next_chap.start_time - current.end_time
                issues.append(
                    f"章节间隙: {current.chapter_index} 与 {next_chap.chapter_index} "
                    f"之间有 {gap:.1f}s 间隙"
                )

            # 检查倒序
            if current.start_time > next_chap.start_time:
                issues.append(
                    f"章节顺序错误: {current.chapter_index} 的开始时间 "
                    f"({current.start_time}) 晚于 {next_chap.chapter_index} ({next_chap.start_time})"
                )

        return issues

    def _assign_cue_to_chapter(
        self,
        cue: TranscriptCue,
        chapters: List[Chapter]
    ) -> Optional[Chapter]:
        """
        为单个 cue 分配 chapter（核心算法）

        匹配规则：
        - 使用左闭右开区间 [start_time, end_time)
        - 如果有多个 chapter 满足（重叠），选择第一个（chapter_index 最小）
        - 如果时间超出所有 chapter 范围，返回 None（由调用方处理）

        Args:
            cue: TranscriptCue 对象
            chapters: Chapter 列表（按时间排序）

        Returns:
            Optional[Chapter]: 匹配的 Chapter，如果超出范围返回 None
        """
        if not chapters:
            return None

        # 遍历 chapters，找到第一个满足条件的
        for chapter in chapters:
            if chapter.start_time <= cue.start_time < chapter.end_time:
                return chapter

        # 超出所有 chapter 范围
        return None
