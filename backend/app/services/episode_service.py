"""
Episode 业务逻辑服务

提供 Episode 相关的业务逻辑方法，包括显示标题生成。
"""

from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs

from app.models import Episode
from app.utils.title_utils import sanitize_title


class EpisodeService:
    """Episode 业务逻辑服务"""

    @staticmethod
    def get_display_title(episode: Episode) -> str:
        """
        获取 Episode 的显示标题，支持多级回退策略。

        优先级:
        1. 原始 title（非空且非纯空格）
        2. show_name（如果存在）
        3. audio_path 提取文件名
        4. source_url 解析（YouTube/Bilibili 标题）
        5. 兜底: "Episode #{id}"

        Args:
            episode: Episode 实例

        Returns:
            str: 显示标题（已清理，跨平台兼容）
        """
        raw_title = EpisodeService._get_raw_title(episode)
        return sanitize_title(raw_title)

    @staticmethod
    def _get_raw_title(episode: Episode) -> str:
        """
        获取原始标题（回退逻辑，未清理）。

        Args:
            episode: Episode 实例

        Returns:
            str: 原始标题
        """
        # 1. 检查原始 title
        if episode.title and episode.title.strip():
            return episode.title

        # 2. 尝试使用 show_name
        if episode.show_name and episode.show_name.strip():
            return f"{episode.show_name.strip()} - Episode #{episode.id}"

        # 3. 尝试从 audio_path 提取文件名
        if episode.audio_path:
            filename = Path(episode.audio_path).stem
            if filename:
                return filename

        # 4. 尝试从 source_url 解析
        if episode.source_url:
            url_title = EpisodeService._parse_url_title(episode.source_url)
            if url_title:
                return url_title

        # 5. 兜底方案
        return f"Episode #{episode.id}"

    @staticmethod
    def _parse_url_title(url: str) -> Optional[str]:
        """
        从 URL 解析有意义的标题标识。

        Args:
            url: 视频 URL

        Returns:
            Optional[str]: 解析出的标题，无法解析则返回 None
        """
        try:
            parsed = urlparse(url)

            # YouTube
            if "youtube.com" in parsed.netloc or "youtu.be" in parsed.netloc:
                if parsed.netloc == "youtu.be":
                    video_id = parsed.path.lstrip("/")
                else:
                    query = parse_qs(parsed.query)
                    video_id = query.get("v", [None])[0]
                if video_id:
                    return f"YouTube Video {video_id}"

            # Bilibili
            elif "bilibili.com" in parsed.netloc:
                # 提取 BV 号或 av 号
                path_parts = parsed.path.split("/")
                for part in path_parts:
                    if part.startswith(("BV", "av")):
                        return f"Bilibili {part}"

            # 通用 URL：返回域名
            if parsed.netloc:
                return f"Video from {parsed.netloc}"

        except Exception:
            pass

        return None
