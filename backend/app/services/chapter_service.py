"""
Chapter 业务逻辑服务

提供 Chapter 相关的业务逻辑方法，包括显示标题生成。
"""

from typing import Optional

from app.models import Chapter, Episode
from app.services.episode_service import EpisodeService
from app.utils.title_utils import sanitize_title


class ChapterService:
    """Chapter 业务逻辑服务"""

    @staticmethod
    def get_display_title(chapter: Chapter, episode: Episode) -> str:
        """
        获取 Chapter 的显示标题，支持多级回退策略。

        优先级:
        1. 原始 title（非空且非纯空格）
        2. 时间范围格式化
        3. 简化序号
        4. 带 Episode 标题的兜底

        Args:
            chapter: Chapter 实例
            episode: 所属 Episode 实例

        Returns:
            str: 显示标题（已清理，跨平台兼容）
        """
        raw_title = ChapterService._get_raw_title(chapter, episode)
        return sanitize_title(raw_title)

    @staticmethod
    def _get_raw_title(chapter: Chapter, episode: Episode) -> str:
        """
        获取原始标题（回退逻辑，未清理）。

        Args:
            chapter: Chapter 实例
            episode: 所属 Episode 实例

        Returns:
            str: 原始标题
        """
        # 1. 检查原始 title
        if chapter.title and chapter.title.strip():
            return chapter.title

        # 2. 尝试使用时间范围
        if chapter.start_time > 0 or chapter.end_time > 0:
            return ChapterService._format_time_range(
                chapter.chapter_index,
                chapter.start_time,
                chapter.end_time
            )

        # 3. 简化序号
        if chapter.start_time == 0 and chapter.end_time == 0:
            return f"Chapter {chapter.chapter_index + 1}"

        # 4. 兜底：使用 Episode 标题
        episode_title = EpisodeService.get_display_title(episode)
        return f"{episode_title} - Section {chapter.chapter_index + 1}"

    @staticmethod
    def _format_time_range(index: int, start_time: float, end_time: float) -> str:
        """
        格式化时间范围为可读字符串。

        Args:
            index: 章节序号（从0开始）
            start_time: 开始时间（秒）
            end_time: 结束时间（秒）

        Returns:
            str: 格式化后的时间范围字符串
        """
        start_str = ChapterService._format_seconds(start_time)
        end_str = ChapterService._format_seconds(end_time)
        return f"Chapter {index + 1} ({start_str}-{end_str})"

    @staticmethod
    def _format_seconds(seconds: float) -> str:
        """
        将秒数转换为 HH:MM 格式。

        Args:
            seconds: 秒数

        Returns:
            str: 格式化后的时间字符串
        """
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"
