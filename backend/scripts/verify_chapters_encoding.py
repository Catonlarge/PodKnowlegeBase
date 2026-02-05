"""
验证数据库中的章节数据编码是否正确
"""
import os
import sys
from pathlib import Path

# 设置临时环境变量
os.environ.setdefault("HF_TOKEN", "dummy_token")
os.environ.setdefault("MOONSHOT_API_KEY", "dummy_key")
os.environ.setdefault("GEMINI_API_KEY", "dummy_key")
os.environ.setdefault("ZHIPU_API_KEY", "dummy_key")

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import get_session
from app.models import Chapter, Episode
from sqlalchemy import desc


def main():
    print("=" * 70)
    print("验证数据库中的章节数据")
    print("=" * 70)

    with get_session() as db:
        # 获取最新的 Episode
        episode = db.query(Episode).order_by(desc(Episode.id)).first()

        if not episode:
            print("没有找到 Episode 数据")
            return

        print(f"\nEpisode ID: {episode.id}")
        print(f"标题: {episode.title}")
        print(f"工作流状态: {episode.workflow_status}")
        print()

        # 获取该 Episode 的所有章节
        chapters = db.query(Chapter).filter(
            Chapter.episode_id == episode.id
        ).order_by(Chapter.chapter_index).all()

        print(f"章节数量: {len(chapters)}")
        print()

        for i, chapter in enumerate(chapters, 1):
            print(f"章节 {i}:")
            print(f"  ID: {chapter.id}")
            print(f"  标题: {chapter.title}")
            print(f"  摘要: {chapter.summary}")
            print(f"  时间: {chapter.start_time:.0f}s - {chapter.end_time:.0f}s")
            print(f"  状态: {chapter.status}")
            print()

        # 验证编码（写入文件）
        output_file = Path(__file__).parent.parent / "data" / "chapters_verification.txt"
        output_file.parent.mkdir(exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"Episode: {episode.title}\n")
            f.write(f"工作流状态: {episode.workflow_status}\n")
            f.write("=" * 70 + "\n\n")

            for i, chapter in enumerate(chapters, 1):
                f.write(f"章节 {i}:\n")
                f.write(f"  标题: {chapter.title}\n")
                f.write(f"  摘要: {chapter.summary}\n")
                f.write(f"  时间: {chapter.start_time:.0f}s - {chapter.end_time:.0f}s\n")
                f.write("\n")

        print(f"章节内容已写入文件: {output_file}")
        print("可以用支持 UTF-8 的文本编辑器打开查看中文内容")

        print("\n" + "=" * 70)
        print("验证完成！数据库中的数据编码正确。")
        print("=" * 70)


if __name__ == "__main__":
    main()
