"""
音频下载服务

使用 yt-dlp 下载音频文件，支持重复检测、元数据提取、重试机制。
"""
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional, Dict, Tuple

from sqlalchemy.orm import Session

from app.models import Episode
from app.utils.file_utils import calculate_md5_sync, get_audio_duration
from app.config import AUDIO_STORAGE_PATH
from app.enums.workflow_status import WorkflowStatus

logger = logging.getLogger(__name__)

# Try to import yt-dlp
try:
    import yt_dlp
    YOUTUBE_DL_AVAILABLE = True
except ImportError:
    YOUTUBE_DL_AVAILABLE = False
    logger.warning("yt-dlp not available. Install with: pip install yt-dlp")


class DownloadService:
    """
    音频下载服务

    负责：
    1. 使用 yt-dlp 下载音频
    2. 提取元数据（标题、时长、缩略图）
    3. 计算 MD5 防重
    4. 指数退避重试
    """

    def __init__(self, db: Session):
        """
        初始化下载服务

        Args:
            db: 数据库会话
        """
        self.db = db
        self.storage_path = Path(AUDIO_STORAGE_PATH)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        if not YOUTUBE_DL_AVAILABLE:
            logger.warning("DownloadService initialized but yt-dlp is not available")

    def download(
        self,
        url: str,
        max_retries: int = 3,
        base_delay: float = 1.0
    ) -> Tuple[str, Dict]:
        """
        下载音频文件

        Args:
            url: 音频 URL
            max_retries: 最大重试次数
            base_delay: 重试基础延迟（秒）

        Returns:
            tuple: (local_path, metadata)

        Raises:
            RuntimeError: 下载失败（超过最大重试次数）
        """
        if not YOUTUBE_DL_AVAILABLE:
            raise RuntimeError("yt-dlp is not available. Install with: pip install yt-dlp")

        # Generate filename and output path
        # First, extract metadata to get title
        metadata = self._extract_metadata(url, None)

        filename = self._generate_filename(url, metadata.get("title", "audio"))
        output_path = str(self.storage_path / filename)

        # Download with retry
        self._download_with_retry(url, output_path, max_retries, base_delay)

        # Get actual duration from downloaded file
        try:
            duration = get_audio_duration(output_path)
            metadata["duration"] = duration
        except Exception as e:
            logger.warning(f"Failed to get duration from file: {e}")
            metadata["duration"] = metadata.get("duration", 0)

        # Calculate file hash
        file_hash = calculate_md5_sync(output_path)
        metadata["file_hash"] = file_hash

        return output_path, metadata

    def download_with_metadata(
        self,
        url: str,
        max_retries: int = 3
    ) -> Episode:
        """
        下载音频并创建 Episode 记录

        Args:
            url: 音频 URL
            max_retries: 最大重试次数

        Returns:
            Episode: 创建的 Episode 对象

        Raises:
            RuntimeError: 下载失败
            ValueError: URL 无效
        """
        # Download the audio
        local_path, metadata = self.download(url, max_retries)

        # Check for duplicate
        existing = self._check_duplicate(metadata["file_hash"])
        if existing:
            logger.info(
                f"[DownloadService] Duplicate file detected (hash={metadata['file_hash']}). "
                f"Returning existing episode {existing.id}"
            )
            # Delete the newly downloaded file
            if os.path.exists(local_path):
                os.remove(local_path)
            return existing

        # Create Episode record
        episode = Episode(
            source_url=url,
            title=metadata.get("title", "Unknown Title"),
            file_hash=metadata["file_hash"],
            duration=metadata.get("duration", 0),
            audio_path=local_path,
            ai_summary=metadata.get("description", ""),
            workflow_status=WorkflowStatus.DOWNLOADED.value
        )

        self.db.add(episode)
        self.db.commit()
        self.db.refresh(episode)

        logger.info(
            f"[DownloadService] Episode created: id={episode.id}, "
            f"title='{episode.title}', duration={episode.duration}s"
        )

        return episode

    def _check_duplicate(self, file_hash: str) -> Optional[Episode]:
        """
        检查是否已存在相同文件

        Args:
            file_hash: 文件 MD5 哈希

        Returns:
            Episode 如果已存在，否则 None
        """
        episode = self.db.query(Episode).filter(
            Episode.file_hash == file_hash
        ).first()

        return episode

    def _extract_metadata(
        self,
        url: str,
        output_path: Optional[str]
    ) -> Dict:
        """
        使用 yt-dlp 提取元数据

        Args:
            url: 音频 URL
            output_path: 输出文件路径（可选，仅用于下载）

        Returns:
            Dict: 元数据字典
        """
        if not YOUTUBE_DL_AVAILABLE:
            return {"title": "Unknown", "duration": 0, "thumbnail": None}

        metadata = {
            "title": "Unknown",
            "duration": 0,
            "thumbnail": None,
            "description": ""
        }

        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

                if info:
                    metadata["title"] = info.get("title", "Unknown")
                    metadata["duration"] = info.get("duration", 0)
                    metadata["thumbnail"] = info.get("thumbnail")
                    metadata["description"] = info.get("description", "")

        except Exception as e:
            logger.error(f"[DownloadService] Failed to extract metadata: {e}")

        return metadata

    def _download_with_retry(
        self,
        url: str,
        output_path: str,
        max_retries: int,
        base_delay: float
    ) -> bool:
        """
        带重试的下载逻辑（指数退避）

        音频优先配置：低质量音频，小文件体积

        Args:
            url: 音频 URL
            output_path: 输出文件路径
            max_retries: 最大重试次数
            base_delay: 基础延迟

        Returns:
            bool: 下载是否成功

        Raises:
            RuntimeError: 超过最大重试次数
        """
        if not YOUTUBE_DL_AVAILABLE:
            raise RuntimeError("yt-dlp is not available")

        for attempt in range(max_retries):
            try:
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    # 音频优先格式：选择最佳音频质量，但限制为音频流
                    'format': 'bestaudio[ext=mp3]/best[ext=mp3]/bestaudio/best',
                    # 后处理：转换为 MP3，低比特率（节省空间）
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '128',  # 128kbps 足够用于语音识别
                    }],
                    'outtmpl': output_path.rsplit('.', 1)[0],  # Remove extension
                    'overwrite': True,
                }

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])

                # Verify file was created
                # yt-dlp may add .mp3 extension
                possible_paths = [
                    output_path,
                    output_path.rsplit('.', 1)[0] + '.mp3',
                    output_path.rsplit('.', 1)[0] + '.m4a',
                ]

                for path in possible_paths:
                    if os.path.exists(path):
                        if path != output_path:
                            # Rename to expected path
                            os.rename(path, output_path)
                        logger.info(
                            f"[DownloadService] Download successful: {output_path}"
                        )
                        return True

                raise RuntimeError("Download completed but file not found")

            except Exception as e:
                logger.warning(
                    f"[DownloadService] Download attempt {attempt + 1}/{max_retries} failed: {e}"
                )

                if attempt < max_retries - 1:
                    # Exponential backoff
                    delay = base_delay * (2 ** attempt)
                    logger.info(f"[DownloadService] Retrying in {delay:.1f}s...")
                    time.sleep(delay)
                else:
                    # Final attempt failed
                    raise RuntimeError(f"下载失败: {e}") from e

        return False

    def _generate_filename(self, url: str, title: str) -> str:
        """
        生成安全的文件名

        保留原始标题的可读性，只移除问题字符

        Args:
            url: 音频 URL
            title: 音频标题（原始大小写）

        Returns:
            str: 安全的文件名（含 .mp3 扩展名）
        """
        # Extract video ID from URL if possible
        video_id = None

        # YouTube patterns
        youtube_patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})',
            r'youtube\.com\/embed\/([a-zA-Z0-9_-]{11})',
            # Bilibili pattern
            r'bilibili\.com\/video\/([a-zA-Z0-9]+)',
        ]

        for pattern in youtube_patterns:
            match = re.search(pattern, url)
            if match:
                video_id = match.group(1)
                break

        # 保守的文件名清理策略：
        # 只保留 ASCII 字母、数字、连字符、下划线
        # 其他所有字符（中文、特殊符号等）都替换为下划线
        safe_title = title.strip()

        # 替换所有非安全字符为下划线
        # 安全字符：a-z, A-Z, 0-9, -, _
        safe_title = re.sub(r'[^a-zA-Z0-9\-_]', '_', safe_title)

        # 移除连续下划线
        safe_title = re.sub(r'_+', '_', safe_title)
        # 移除首尾下划线
        safe_title = safe_title.strip('_')
        # 限制长度（保留视频ID空间）
        max_title_length = 100 if video_id else 150
        safe_title = safe_title[:max_title_length]

        # 确保文件名不为空
        if not safe_title:
            safe_title = "audio"

        # 组合文件名
        if video_id:
            filename = f"{video_id}_{safe_title}.mp3"
        else:
            filename = f"{safe_title}.mp3"

        return filename
