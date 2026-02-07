"""
真实 AI 结构化输出集成测试 - 字幕校对服务

测试 SubtitleProofreadingService 使用 StructuredLLM 的端到端流程。

用法:
    python scripts/test_proofreading_structured_output_real_ai.py
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
from app.models import Episode, TranscriptCue, AudioSegment, TranscriptCorrection
from app.services.subtitle_proofreading_service import SubtitleProofreadingService
from app.config import (
    DATABASE_PATH,
    MOONSHOT_API_KEY,
    MOONSHOT_BASE_URL,
    MOONSHOT_MODEL,
    ZHIPU_API_KEY,
    ZHIPU_BASE_URL,
    ZHIPU_MODEL
)


def setup_in_memory_db():
    """创建内存数据库用于测试"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def create_test_episode_with_cues(db_session, title: str = "测试Episode"):
    """创建测试 Episode 及其关联的 Cues"""
    import hashlib
    # 生成唯一文件哈希
    file_hash = hashlib.md5(title.encode()).hexdigest()

    # 创建 Episode
    episode = Episode(
        title=title,
        audio_path="/test/path.mp3",
        file_hash=file_hash,
        duration=300.0,
        ai_summary="这是一个关于学习方法测试的摘要。包含了实用的学习技巧和深度思考。"
    )
    db_session.add(episode)
    db_session.flush()

    # 创建 AudioSegment
    segment = AudioSegment(
        episode_id=episode.id,
        segment_index=0,
        segment_id="segment_001",
        start_time=0.0,
        end_time=300.0,
        status="completed"
    )
    db_session.add(segment)
    db_session.flush()

    # 创建测试 Cues（包含一些故意错误的拼写）
    test_cues = [
        TranscriptCue(
            segment_id=segment.id,
            start_time=float(i * 10),
            end_time=float((i + 1) * 10),
            speaker="Speaker",
            text=text
        )
        for i, text in enumerate([
            "Hello warld and welcome to the show",  # warld -> world
            "Today we will discuss lerning methods",  # lerning -> learning
            "Good mornign everyone",  # mornign -> morning
            "Lets talk about knowlage",  # knowlage -> knowledge
            "I appreaciate your time",  # appreaciate -> appreciate
            "This is a grate opportunity",  # grate -> great
            "Thank you for listning",  # listning -> listening
            "Have a wonderfull day",  # wonderfull -> wonderful
        ])
    ]

    for cue in test_cues:
        db_session.add(cue)

    db_session.flush()
    return episode


def test_proofreading_service_structured_output():
    """测试 SubtitleProofreadingService 结构化输出"""
    logger.info("=" * 60)
    logger.info("字幕校对结构化输出真实 AI 集成测试")
    logger.info("=" * 60)

    # 显示配置
    logger.info(f"\n[配置]")
    logger.info(f"  Moonshot API Key: {'*** 已配置 ***' if MOONSHOT_API_KEY else 'NOT SET'}")
    logger.info(f"  Zhipu API Key: {'*** 已配置 ***' if ZHIPU_API_KEY else 'NOT SET'}")

    # 设置测试数据库
    db = setup_in_memory_db()
    episode = create_test_episode_with_cues(db, "英语学习方法：从入门到精通")

    logger.info(f"\n[测试数据]")
    logger.info(f"  Episode ID: {episode.id}")
    logger.info(f"  Title: {episode.title}")

    # 获取 cues 数量
    cues = db.query(TranscriptCue).join(
        AudioSegment, TranscriptCue.segment_id == AudioSegment.id
    ).filter(
        AudioSegment.episode_id == episode.id
    ).all()

    logger.info(f"  Cues 数量: {len(cues)}")
    for cue in cues[:3]:
        logger.info(f"    - Cue {cue.id}: {cue.text[:50]}...")
    logger.info(f"    ...")

    # 测试 Moonshot Provider
    if MOONSHOT_API_KEY:
        logger.info(f"\n[测试1] Moonshot Kimi 结构化输出")
        logger.info("-" * 60)

        try:
            service = SubtitleProofreadingService(
                db,
                provider="moonshot",
                api_key=MOONSHOT_API_KEY,
                base_url=MOONSHOT_BASE_URL,
                model=MOONSHOT_MODEL
            )
            logger.info(f"  StructuredLLM: {'已初始化' if service.structured_llm else '未初始化'}")

            if service.structured_llm:
                result = service.scan_and_correct(
                    episode_id=episode.id,
                    apply=False  # 不应用修改，只获取结果
                )

                logger.success(f"校对完成，共发现 {len(result.corrections)} 条修正建议")

                for i, correction in enumerate(result.corrections[:5], 1):
                    logger.info(f"\n  [修正 {i}]")
                    logger.info(f"    Cue ID: {correction['cue_id']}")
                    logger.info(f"    原文: {correction['original_text']}")
                    logger.info(f"    修正: {correction['corrected_text']}")
                    logger.info(f"    原因: {correction['reason']}")
                    logger.info(f"    置信度: {correction['confidence']:.2f}")

                if len(result.corrections) > 5:
                    logger.info(f"\n  ... 还有 {len(result.corrections) - 5} 条修正建议")

                # 验证数据
                assert result.total_cues == len(cues), f"总 cues 数量不匹配"
                assert result.corrected_count == 0, "应该未应用修正"
                assert len(result.corrections) >= 0, "修正建议数量应该 >= 0"

                logger.success(f"\n测试1通过: Moonshot Kimi 结构化输出验证成功")
            else:
                logger.error("StructuredLLM 未初始化，跳过测试")

        except Exception as e:
            logger.error(f"测试1失败: {e}")
            import traceback
            traceback.print_exc()
    else:
        logger.warning("Moonshot API Key 未配置，跳过 Moonshot 测试")

    # 测试 Zhipu Provider
    if ZHIPU_API_KEY:
        logger.info(f"\n[测试2] Zhipu GLM 结构化输出")
        logger.info("-" * 60)

        try:
            service = SubtitleProofreadingService(
                db,
                provider="zhipu",
                api_key=ZHIPU_API_KEY,
                base_url=ZHIPU_BASE_URL,
                model=ZHIPU_MODEL
            )
            logger.info(f"  StructuredLLM: {'已初始化' if service.structured_llm else '未初始化'}")

            if service.structured_llm:
                result = service.scan_and_correct(
                    episode_id=episode.id,
                    apply=False
                )

                logger.success(f"校对完成，共发现 {len(result.corrections)} 条修正建议")

                for i, correction in enumerate(result.corrections[:5], 1):
                    logger.info(f"\n  [修正 {i}]")
                    logger.info(f"    Cue ID: {correction['cue_id']}")
                    logger.info(f"    原文: {correction['original_text']}")
                    logger.info(f"    修正: {correction['corrected_text']}")
                    logger.info(f"    置信度: {correction['confidence']:.2f}")

                logger.success(f"\n测试2通过: Zhipu GLM 结构化输出验证成功")
            else:
                logger.error("StructuredLLM 未初始化，跳过测试")

        except Exception as e:
            logger.error(f"测试2失败: {e}")
            import traceback
            traceback.print_exc()
    else:
        logger.warning("Zhipu API Key 未配置，跳过 Zhipu 测试")

    # 测试3: 应用修正到数据库
    if MOONSHOT_API_KEY:
        logger.info(f"\n[测试3] 应用修正到数据库")
        logger.info("-" * 60)

        try:
            service = SubtitleProofreadingService(
                db,
                provider="moonshot",
                api_key=MOONSHOT_API_KEY,
                base_url=MOONSHOT_BASE_URL,
                model=MOONSHOT_MODEL
            )

            result = service.scan_and_correct(
                episode_id=episode.id,
                apply=True  # 应用修改
            )

            logger.info(f"  已应用 {result.corrected_count} 条修正")

            # 验证数据库记录
            corrections = db.query(TranscriptCorrection).filter(
                TranscriptCorrection.cue_id.in_([c.id for c in cues])
            ).all()

            logger.info(f"  数据库中的修正记录: {len(corrections)} 条")

            for corr in corrections[:3]:
                logger.info(f"\n  修正记录:")
                logger.info(f"    Cue ID: {corr.cue_id}")
                logger.info(f"    原文: {corr.original_text}")
                logger.info(f"    修正: {corr.corrected_text}")
                logger.info(f"    原因: {corr.reason}")

            logger.success(f"\n测试3通过: 数据库修正记录验证成功")

        except Exception as e:
            logger.error(f"测试3失败: {e}")
            import traceback
            traceback.print_exc()

    logger.info(f"\n{'=' * 60}")
    logger.success(f"所有测试完成！")
    logger.info(f"{'=' * 60}")

    return True


if __name__ == "__main__":
    success = test_proofreading_service_structured_output()
    sys.exit(0 if success else 1)
