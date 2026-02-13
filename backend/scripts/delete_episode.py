#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
删除指定 Episode 及其所有关联数据（生产数据库）

用法:
    python scripts/delete_episode.py <episode_id>

示例:
    python scripts/delete_episode.py 19

注意: 需在 backend/ 目录下执行，使用 config.yaml 中的 database.path
"""
import sys
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, str(Path(__file__).parent.parent))

BACKEND_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = BACKEND_DIR / "delete_episode_log.txt"


_log_first = True


def _log(msg: str) -> None:
    """打印并写入日志（便于诊断终端输出捕获问题）"""
    global _log_first
    print(msg, flush=True)
    try:
        mode = "w" if _log_first else "a"
        with open(LOG_FILE, mode, encoding="utf-8") as f:
            if _log_first:
                f.write(f"[{datetime.now().isoformat()}] 开始执行\n")
                _log_first = False
            f.write(msg + "\n")
    except OSError:
        pass


from app.database import get_session
from app.config import DATABASE_PATH
from app.models import (
    Episode,
    AudioSegment,
    TranscriptCue,
    Translation,
    Chapter,
    MarketingPost,
    PublicationRecord,
    TranscriptCorrection,
    TranslationCorrection,
)


def delete_episode(episode_id: int) -> bool:
    """删除 Episode 及所有关联数据（按 FK 依赖顺序）"""
    with get_session() as db:
        episode = db.get(Episode, episode_id)
        if not episode:
            return False

        # 获取该 episode 的 segment ids
        segment_ids = [s.id for s in db.query(AudioSegment).filter(
            AudioSegment.episode_id == episode_id
        ).all()]

        # 获取该 episode 的 cue ids（通过 segment）
        cue_ids = []
        if segment_ids:
            cues = db.query(TranscriptCue).filter(
                TranscriptCue.segment_id.in_(segment_ids)
            ).all()
            cue_ids = [c.id for c in cues]

        # 1. TranscriptCorrection (refs transcript_cue)
        if cue_ids:
            db.query(TranscriptCorrection).filter(
                TranscriptCorrection.cue_id.in_(cue_ids)
            ).delete(synchronize_session=False)

        # 2. TranslationCorrection (refs transcript_cue)
        if cue_ids:
            db.query(TranslationCorrection).filter(
                TranslationCorrection.cue_id.in_(cue_ids)
            ).delete(synchronize_session=False)

        # 3. Translation (refs transcript_cue)
        if cue_ids:
            db.query(Translation).filter(
                Translation.cue_id.in_(cue_ids)
            ).delete(synchronize_session=False)

        # 4. MarketingPost (refs episode, chapter)
        db.query(MarketingPost).filter(
            MarketingPost.episode_id == episode_id
        ).delete(synchronize_session=False)

        # 5. PublicationRecord (refs episode)
        db.query(PublicationRecord).filter(
            PublicationRecord.episode_id == episode_id
        ).delete(synchronize_session=False)

        # 6. TranscriptCue
        if segment_ids:
            db.query(TranscriptCue).filter(
                TranscriptCue.segment_id.in_(segment_ids)
            ).delete(synchronize_session=False)

        # 7. Chapter
        db.query(Chapter).filter(
            Chapter.episode_id == episode_id
        ).delete(synchronize_session=False)

        # 8. AudioSegment
        db.query(AudioSegment).filter(
            AudioSegment.episode_id == episode_id
        ).delete(synchronize_session=False)

        # 9. Episode
        db.delete(episode)

    return True


def main():
    if len(sys.argv) < 2:
        _log("用法: python scripts/delete_episode.py <episode_id>")
        sys.exit(1)

    try:
        episode_id = int(sys.argv[1])
    except ValueError:
        _log("episode_id 必须是整数")
        sys.exit(1)

    _log(f"数据库: {DATABASE_PATH}")
    _log(f"正在删除 Episode {episode_id}...")

    if delete_episode(episode_id):
        _log(f"已删除 Episode {episode_id} 及所有关联数据")
    else:
        _log(f"Episode {episode_id} 不存在")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        err_msg = f"执行失败: {e}"
        try:
            print(err_msg, flush=True)
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(err_msg + "\n")
        except Exception:
            pass
        raise
