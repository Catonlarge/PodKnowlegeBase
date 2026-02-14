#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复「文件已下载但数据库未写入」的 Episode

当 download_episode 因异常（如 tuple 赋值错误）导致 commit 失败时，
音频文件可能已下载到 audios 目录，但 episode 的 audio_path、workflow_status 未更新。

用法:
  # 1. 进入 backend 目录并激活虚拟环境
  cd D:\programming_enviroment\EnglishPod-knowledgeBase\backend
  venv-kb\Scripts\Activate.ps1

  # 2. 运行修复脚本
  python scripts/repair_downloaded_episode.py                    # 修复所有匹配的 episode
  python scripts/repair_downloaded_episode.py BV17ycez5EAQ      # 按视频 ID 修复
  python scripts/repair_downloaded_episode.py --dry-run         # 仅预览，不写入
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import or_

from app.config import AUDIO_STORAGE_PATH
from app.database import get_session
from app.models import Episode
from app.enums.workflow_status import WorkflowStatus
from app.utils.file_utils import get_audio_duration


def find_matching_audio(video_id: str) -> Path | None:
    """在 audios 目录中查找以 video_id 开头的音频文件"""
    storage = Path(AUDIO_STORAGE_PATH)
    if not storage.exists():
        return None
    for f in storage.iterdir():
        if f.is_file() and f.name.startswith(f"{video_id}_") and f.suffix.lower() in (".mp3", ".m4a", ".webm"):
            return f
    return None


def repair_episode(episode: Episode, audio_path: Path, dry_run: bool) -> bool:
    """更新 episode 的 audio_path、title、duration、workflow_status"""
    parts = audio_path.stem.split("_", 1)
    title_from_file = parts[1].replace("_", " ") if len(parts) > 1 else audio_path.stem

    try:
        duration = get_audio_duration(str(audio_path))
    except Exception as e:
        print(f"  警告: 无法获取时长 ({e})，使用 0")
        duration = 0

    print(f"  将更新: audio_path={audio_path}")
    print(f"          title={title_from_file[:60]}{'...' if len(title_from_file) > 60 else ''}")
    print(f"          duration={duration:.1f}s")
    print(f"          workflow_status=DOWNLOADED(1)")

    if not dry_run:
        episode.audio_path = str(audio_path)
        episode.title = title_from_file or episode.title or "Unknown"
        episode.duration = duration
        episode.workflow_status = WorkflowStatus.DOWNLOADED.value
    return True


def main():
    parser = argparse.ArgumentParser(description="修复已下载但数据库未写入的 Episode")
    parser.add_argument("video_id", nargs="?", help="Bilibili 视频 ID，如 BV17ycez5EAQ；不传则修复所有 audio_path 为空且 source_url 可解析的")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写入数据库")
    args = parser.parse_args()

    with get_session() as db:
        if args.video_id:
            # 按 video_id 查找
            episodes = db.query(Episode).filter(
                Episode.source_url.like(f"%{args.video_id}%"),
                Episode.workflow_status == WorkflowStatus.INIT.value,
            ).all()
            if not episodes:
                episodes = db.query(Episode).filter(Episode.source_url.like(f"%{args.video_id}%")).all()
        else:
            # 查找 audio_path 为空或 None 的
            episodes = db.query(Episode).filter(
                or_(Episode.audio_path.is_(None), Episode.audio_path == ""),
                Episode.source_url.isnot(None),
            ).all()

        if not episodes:
            print("未找到需要修复的 Episode")
            return 0

        print(f"找到 {len(episodes)} 个待修复的 Episode")
        repaired = 0

        for ep in episodes:
            # 从 source_url 解析 video_id
            url = ep.source_url or ""
            video_id = None
            if "bilibili.com/video/" in url:
                import re
                m = re.search(r"bilibili\.com/video/([a-zA-Z0-9]+)", url)
                if m:
                    video_id = m.group(1)
            if not video_id and args.video_id:
                video_id = args.video_id

            if not video_id:
                print(f"  Episode {ep.id}: 无法解析 video_id，跳过")
                continue

            audio_file = find_matching_audio(video_id)
            if not audio_file:
                print(f"  Episode {ep.id}: 未找到匹配的音频文件 (video_id={video_id})")
                continue

            print(f"\nEpisode {ep.id} (source_url 含 {video_id}):")
            if repair_episode(ep, audio_file, args.dry_run):
                repaired += 1

        if repaired and not args.dry_run:
            db.commit()
            print(f"\n已修复 {repaired} 个 Episode")
        elif args.dry_run:
            print(f"\n[dry-run] 将修复 {repaired} 个 Episode，去掉 --dry-run 后执行")

    return 0


if __name__ == "__main__":
    sys.exit(main())
