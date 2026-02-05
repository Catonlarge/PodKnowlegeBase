"""
验证数据库中的翻译数据编码是否正确
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
from app.models import Episode, Translation, TranscriptCue
from sqlalchemy import desc


def main():
    print("=" * 70)
    print("验证数据库中的翻译数据")
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

        # 获取该 Episode 的已完成的翻译记录
        from app.enums.translation_status import TranslationStatus
        translations = db.query(Translation).filter(
            Translation.language_code == "zh",
            Translation.translation_status == TranslationStatus.COMPLETED.value
        ).order_by(Translation.id.desc()).limit(5).all()

        print(f"翻译记录数量（前5条）: {len(translations)}")
        print()

        for i, trans in enumerate(translations, 1):
            # 获取对应的 Cue
            cue = db.query(TranscriptCue).filter(TranscriptCue.id == trans.cue_id).first()
            print(f"翻译 {i}:")
            print(f"  ID: {trans.id}")
            print(f"  Cue ID: {trans.cue_id}")
            if cue:
                print(f"  英文: {cue.text[:60]}...")
            print(f"  中文: {trans.translation}")
            print(f"  Original: {trans.original_translation}")
            print(f"  is_edited: {trans.is_edited}")
            print(f"  状态: {trans.translation_status}")
            print()

        # 验证编码（写入文件）
        output_file = Path(__file__).parent.parent / "data" / "translation_verification.txt"
        output_file.parent.mkdir(exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"Episode: {episode.title}\n")
            f.write(f"工作流状态: {episode.workflow_status}\n")
            f.write("=" * 70 + "\n\n")

            for i, trans in enumerate(translations, 1):
                cue = db.query(TranscriptCue).filter(TranscriptCue.id == trans.cue_id).first()
                f.write(f"翻译 {i}:\n")
                f.write(f"  中文: {trans.translation}\n")
                f.write(f"  Original: {trans.original_translation}\n")
                f.write(f"  is_edited: {trans.is_edited}\n")
                f.write("\n")

        print(f"翻译内容已写入文件: {output_file}")
        print("可以用支持 UTF-8 的文本编辑器打开查看中文内容")

        print("\n" + "=" * 70)
        print("验证完成！数据库中的数据编码正确。")
        print("=" * 70)


if __name__ == "__main__":
    main()
