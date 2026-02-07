"""
测试 Episode 19 的翻译服务（使用新的批次降级策略）
"""
import logging
import sys
import io
import os
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 使用生产数据库
# os.environ["DATABASE_URL"] = "sqlite:///D:/programming_enviroment/EnglishPod-knowledgeBase/backend/data/episodes_test.db"

# 设置 UTF-8 编码输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 设置日志级别
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)

from app.database import get_session
from app.services.translation_service import TranslationService
from app.services.ai.ai_service import AIService
from app.models import Episode, Translation
from app.enums.translation_status import TranslationStatus
from sqlalchemy import func


def main():
    print("=" * 70)
    print("Episode 19 翻译测试（批次降级策略）")
    print("=" * 70)

    with get_session() as db:
        episode = db.query(Episode).filter(Episode.id == 19).first()
        if not episode:
            print("Episode 19 不存在")
            return

        print(f"\nEpisode: {episode.title} (ID: {episode.id})")

        # 查看当前翻译状态
        stats = db.query(
            Translation.translation_status,
            func.count(Translation.id)
        ).filter(
            Translation.language_code == "zh"
        ).group_by(Translation.translation_status).all()

        print("\n当前翻译状态:")
        print("-" * 70)
        for status, count in stats:
            print(f"  {status}: {count}")

        total_translations = db.query(Translation).filter(
            Translation.language_code == "zh"
        ).count()
        print(f"  总计: {total_translations}")

        # 创建翻译服务（不传 api_key，让它从配置中读取）
        translation_service = TranslationService(
            db,
            provider="moonshot"
        )

        print("\n" + "=" * 70)
        print("开始批量翻译...")
        print("=" * 70)

        # 执行批量翻译
        success_count = translation_service.batch_translate(
            episode.id,
            language_code="zh"
        )

        print("\n" + "=" * 70)
        print("翻译完成!")
        print("=" * 70)
        print(f"成功翻译: {success_count} 条")

        # 查看翻译后状态
        stats = db.query(
            Translation.translation_status,
            func.count(Translation.id)
        ).filter(
            Translation.language_code == "zh"
        ).group_by(Translation.translation_status).all()

        print("\n翻译后状态:")
        print("-" * 70)
        for status, count in stats:
            print(f"  {status}: {count}")

        total_translations = db.query(Translation).filter(
            Translation.language_code == "zh"
        ).count()
        print(f"  总计: {total_translations}")


if __name__ == "__main__":
    main()
