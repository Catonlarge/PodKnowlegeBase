"""
调试 Episode 1 的数据

检查 Episode 1 是否有 Chapters 和 Cues 数据
"""
import io
import sys
from pathlib import Path

# Windows UTF-8 编码处理
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Episode, Chapter, TranscriptCue, Translation, AudioSegment
from app.config import DATABASE_PATH


def main():
    """主函数"""
    # 检查两个数据库
    databases = [
        ("生产数据库", DATABASE_PATH),
        ("测试数据库", "D:/programming_enviroment/EnglishPod-knowledgeBase/backend/data/test_integration.db")
    ]

    for db_name, db_path in databases:
        print("=" * 60)
        print(f"{db_name}: {db_path}")
        print("=" * 60)

        # 创建数据库连接
        engine = create_engine(f"sqlite:///{db_path}")
        SessionLocal = sessionmaker(bind=engine)
        db = SessionLocal()

        try:
            episode_id = 1

            # 获取 Episode
            episode = db.get(Episode, episode_id)

            if not episode:
                print(f"Episode {episode_id} 不存在\n")
                continue

            print(f"标题: {episode.title}")
            print(f"AI 摘要: {episode.ai_summary or '(无)'}")
            print(f"工作流状态: {episode.workflow_status}")

            # 检查 AudioSegments
            segments = db.query(AudioSegment).filter(
                AudioSegment.episode_id == episode_id
            ).all()

            print(f"AudioSegment 数量: {len(segments)}")

            # 检查 Chapters
            chapters = db.query(Chapter).filter(
                Chapter.episode_id == episode_id
            ).order_by(Chapter.start_time).all()

            print(f"章节数量: {len(chapters)}")

            if chapters:
                for chapter in chapters[:3]:  # 只显示前3个
                    print(f"  - {chapter.chapter_index + 1}: {chapter.title}")

            # 检查所有 TranscriptCues（通过 Segment 关联）
            total_cues = db.query(TranscriptCue).join(
                AudioSegment, TranscriptCue.segment_id == AudioSegment.id
            ).filter(
                AudioSegment.episode_id == episode_id
            ).count()

            print(f"字幕 Cue 总数: {total_cues}\n")

        finally:
            db.close()
            engine.dispose()


if __name__ == "__main__":
    main()
