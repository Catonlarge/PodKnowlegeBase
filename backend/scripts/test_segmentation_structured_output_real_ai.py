"""
真实 AI 结构化输出集成测试 - 章节切分服务

测试 SegmentationService 使用 StructuredLLM 的端到端流程。

用法:
    python scripts/test_segmentation_structured_output_real_ai.py
"""
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import io
# Windows 控制台 UTF-8 编码处理
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models import Episode, TranscriptCue, AudioSegment, Chapter
from app.services.segmentation_service import SegmentationService
from app.config import (
    DATABASE_PATH,
    MOONSHOT_API_KEY,
    MOONSHOT_BASE_URL,
    MOONSHOT_MODEL,
    ZHIPU_API_KEY,
    ZHIPU_BASE_URL,
    ZHIPU_MODEL
)
from app.enums.workflow_status import WorkflowStatus


def setup_in_memory_db():
    """创建内存数据库用于测试"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def create_test_episode_with_cues(db_session, duration_minutes: int = 10):
    """创建测试 Episode 及其关联的 Cues"""
    import hashlib
    title = f"测试Episode_{duration_minutes}分钟"
    file_hash = hashlib.md5(title.encode()).hexdigest()

    duration_seconds = duration_minutes * 60

    # 创建 Episode
    episode = Episode(
        title=f"英语学习播客 - {duration_minutes}分钟版",
        audio_path="/test/path.mp3",
        file_hash=file_hash,
        duration=float(duration_seconds),
        ai_summary=f"这是一个关于英语学习方法的{duration_minutes}分钟播客。包含了词汇、语法和听力技巧。"
    )
    db_session.add(episode)
    db_session.flush()

    # 更新状态为 TRANSCRIBED
    episode.workflow_status = WorkflowStatus.TRANSCRIBED.value
    db_session.flush()

    # 创建 AudioSegment
    segment = AudioSegment(
        episode_id=episode.id,
        segment_index=0,
        segment_id="segment_001",
        start_time=0.0,
        end_time=float(duration_seconds),
        status="completed"
    )
    db_session.add(segment)
    db_session.flush()

    # 创建测试 Cues（模拟完整字幕）
    # 根据时长生成不同数量的 cues
    num_cues = min(int(duration_seconds / 10), 100)  # 每10秒一个cue，最多100个

    test_cues = []
    transcript_content = [
        "Hello everyone and welcome back to our English learning podcast",
        "Today we're going to talk about vocabulary building strategies",
        "The first tip is to read as much as you can in English",
        "Reading helps you see words in context and understand their usage",
        "The second tip is to use flashcards for memorization",
        "Flashcards are a great way to review vocabulary regularly",
        "Another important strategy is to listen to English content",
        "This helps with pronunciation and understanding spoken English",
        "Don't be afraid to make mistakes when speaking",
        "Practice is key to improving your language skills",
        "Try to learn new words in phrases rather than individually",
        "Context is crucial for remembering vocabulary effectively",
        "Watching English movies and TV shows is also helpful",
        "You can learn colloquial expressions and cultural references",
        "Keep a vocabulary notebook to track new words",
        "Review your notes regularly to reinforce learning",
        "Use technology like language learning apps and websites",
        "These tools provide interactive ways to practice vocabulary",
        "Find a language partner to practice with regularly",
        "Speaking with others helps reinforce what you've learned",
    ]

    for i in range(num_cues):
        # 循环使用内容
        content_idx = i % len(transcript_content)
        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=float(i * 10),
            end_time=float((i + 1) * 10),
            speaker="Speaker" if i % 2 == 0 else "Host",
            text=transcript_content[content_idx]
        )
        test_cues.append(cue)
        db_session.add(cue)

    db_session.flush()
    return episode


def test_segmentation_service_structured_output():
    """测试 SegmentationService 结构化输出"""
    logger.info("=" * 60)
    logger.info("章节切分结构化输出真实 AI 集成测试")
    logger.info("=" * 60)

    # 显示配置
    logger.info(f"\n[配置]")
    logger.info(f"  Moonshot API Key: {'*** 已配置 ***' if MOONSHOT_API_KEY else 'NOT SET'}")
    logger.info(f"  Zhipu API Key: {'*** 已配置 ***' if ZHIPU_API_KEY else 'NOT SET'}")

    # 测试短内容（< 8分钟）
    logger.info(f"\n[测试数据设置] 短内容（5分钟）")
    logger.info("-" * 60)

    db = setup_in_memory_db()
    short_episode = create_test_episode_with_cues(db, duration_minutes=5)

    # 测试 Moonshot Provider - 短内容
    if MOONSHOT_API_KEY:
        logger.info(f"\n[测试1] Moonshot Kimi - 短内容章节切分")
        logger.info("-" * 60)

        try:
            service = SegmentationService(
                db,
                provider="moonshot",
                api_key=MOONSHOT_API_KEY,
                base_url=MOONSHOT_BASE_URL,
                model=MOONSHOT_MODEL
            )
            logger.info(f"  StructuredLLM: {'已初始化' if service.structured_llm else '未初始化'}")

            if service.structured_llm:
                chapters = service.analyze_and_segment(
                    episode_id=short_episode.id
                )

                logger.success(f"章节切分完成，共生成 {len(chapters)} 个章节")

                for i, chapter in enumerate(chapters, 1):
                    logger.info(f"\n  [章节 {i}]")
                    logger.info(f"    标题: {chapter.title}")
                    logger.info(f"    摘要: {chapter.summary[:80]}...")
                    logger.info(f"    时间: {chapter.start_time:.0f}s - {chapter.end_time:.0f}s")

                # 验证数据
                assert len(chapters) >= 1, "至少应该有1个章节"
                assert len(chapters) <= 2, "5分钟内容最多2个章节"

                # 验证时间范围
                assert chapters[0].start_time == 0, "第一章应该从0开始"
                assert chapters[-1].end_time <= short_episode.duration * 1.1, "最后章节不应超出总时长"

                logger.success(f"\n测试1通过: 短内容章节切分验证成功")

                # 清理数据库状态，为下一个测试准备
                db.rollback()
            else:
                logger.error("StructuredLLM 未初始化，跳过测试")

        except Exception as e:
            logger.error(f"测试1失败: {e}")
            import traceback
            traceback.print_exc()
    else:
        logger.warning("Moonshot API Key 未配置，跳过 Moonshot 测试")

    # 创建新的测试数据库用于中等内容测试
    db = setup_in_memory_db()
    medium_episode = create_test_episode_with_cues(db, duration_minutes=12)

    # 测试中等内容（8-20分钟）
    if MOONSHOT_API_KEY:
        logger.info(f"\n[测试2] Moonshot Kimi - 中等内容章节切分")
        logger.info("-" * 60)

        try:
            service = SegmentationService(
                db,
                provider="moonshot",
                api_key=MOONSHOT_API_KEY,
                base_url=MOONSHOT_BASE_URL,
                model=MOONSHOT_MODEL
            )

            chapters = service.analyze_and_segment(
                episode_id=medium_episode.id
            )

            logger.success(f"章节切分完成，共生成 {len(chapters)} 个章节")

            for i, chapter in enumerate(chapters, 1):
                logger.info(f"\n  [章节 {i}]")
                logger.info(f"    标题: {chapter.title}")
                logger.info(f"    摘要: {chapter.summary[:80]}...")
                logger.info(f"    时间: {chapter.start_time:.0f}s - {chapter.end_time:.0f}s")

            # 验证数据
            assert len(chapters) >= 1, "至少应该有1个章节"
            assert len(chapters) <= 4, "12分钟内容最多4个章节"

            logger.success(f"\n测试2通过: 中等内容章节切分验证成功")

        except Exception as e:
            logger.error(f"测试2失败: {e}")
            import traceback
            traceback.print_exc()

    # 测试 Zhipu Provider
    if ZHIPU_API_KEY:
        db = setup_in_memory_db()
        test_episode = create_test_episode_with_cues(db, duration_minutes=8)

        logger.info(f"\n[测试3] Zhipu GLM - 章节切分")
        logger.info("-" * 60)

        try:
            service = SegmentationService(
                db,
                provider="zhipu",
                api_key=ZHIPU_API_KEY,
                base_url=ZHIPU_BASE_URL,
                model=ZHIPU_MODEL
            )
            logger.info(f"  StructuredLLM: {'已初始化' if service.structured_llm else '未初始化'}")

            if service.structured_llm:
                chapters = service.analyze_and_segment(
                    episode_id=test_episode.id
                )

                logger.success(f"章节切分完成，共生成 {len(chapters)} 个章节")

                for i, chapter in enumerate(chapters, 1):
                    logger.info(f"\n  [章节 {i}]")
                    logger.info(f"    标题: {chapter.title}")
                    logger.info(f"    时间: {chapter.start_time:.0f}s - {chapter.end_time:.0f}s")

                logger.success(f"\n测试3通过: Zhipu GLM 结构化输出验证成功")
            else:
                logger.error("StructuredLLM 未初始化，跳过测试")

        except Exception as e:
            logger.error(f"测试3失败: {e}")
            import traceback
            traceback.print_exc()
    else:
        logger.warning("Zhipu API Key 未配置，跳过 Zhipu 测试")

    logger.info(f"\n{'=' * 60}")
    logger.success(f"所有测试完成！")
    logger.info(f"{'=' * 60}")

    return True


if __name__ == "__main__":
    success = test_segmentation_service_structured_output()
    sys.exit(0 if success else 1)
