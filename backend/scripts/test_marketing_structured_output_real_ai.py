"""
真实 AI 结构化输出集成测试 - 营销文案服务

测试 MarketingService 使用 StructuredLLM 的端到端流程。

用法:
    python scripts/test_marketing_structured_output_real_ai.py
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
from app.models import Episode, MarketingPost
from app.services.marketing_service import MarketingService
from app.config import (
    DATABASE_PATH,
    MARKETING_LLM_PROVIDER,
    get_marketing_llm_config
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


def create_test_episode(db_session, title: str = "测试Episode"):
    """创建测试 Episode"""
    import hashlib
    # 生成唯一文件哈希
    file_hash = hashlib.md5(title.encode()).hexdigest()

    episode = Episode(
        title=title,
        audio_path="/test/path.mp3",
        file_hash=file_hash,
        duration=300.0,
        ai_summary="这是一个关于学习方法测试的摘要。包含了实用的学习技巧和深度思考。"
    )
    db_session.add(episode)
    db_session.flush()
    return episode


def test_marketing_service_structured_output():
    """测试 MarketingService 结构化输出"""
    logger.info("=" * 60)
    logger.info("营销文案结构化输出真实 AI 集成测试")
    logger.info("=" * 60)

    # 显示配置
    llm_config = get_marketing_llm_config()
    logger.info(f"\n[配置]")
    logger.info(f"  Provider: {MARKETING_LLM_PROVIDER}")
    logger.info(f"  Model: {llm_config['model']}")
    logger.info(f"  Base URL: {llm_config['base_url']}")
    logger.info(f"  API Key: {'*** 已配置 ***' if llm_config['api_key'] else 'NOT SET'}")

    # 设置测试数据库
    db = setup_in_memory_db()
    episode = create_test_episode(db, "英语学习方法：从入门到精通")

    logger.info(f"\n[测试数据]")
    logger.info(f"  Episode ID: {episode.id}")
    logger.info(f"  Title: {episode.title}")
    logger.info(f"  Summary: {episode.ai_summary[:50]}...")

    # 创建 MarketingService
    try:
        service = MarketingService(db, provider=MARKETING_LLM_PROVIDER)
        logger.info(f"\n[服务初始化]")
        logger.info(f"  StructuredLLM: {'已初始化' if service.structured_llm else '未初始化'}")
        logger.info(f"  OpenAI Client: {'已初始化' if service._openai_client else '未初始化'}")
    except Exception as e:
        logger.error(f"服务初始化失败: {e}")
        return False

    if not service.structured_llm:
        logger.error("StructuredLLM 未初始化，无法进行测试")
        return False

    # 测试1: 生成多角度营销文案（使用 StructuredLLM）
    logger.info(f"\n[测试1] 多角度营销文案生成（使用 StructuredLLM）")
    logger.info("-" * 60)

    try:
        angle_copies = service.generate_xiaohongshu_copy_multi_angle(
            episode_id=episode.id,
            language="zh"
        )

        logger.success(f"成功生成 {len(angle_copies)} 个角度文案")

        for i, copy in enumerate(angle_copies, 1):
            angle_tag = copy.metadata.get("angle_tag", "未知")
            logger.info(f"\n[角度 {i}] {angle_tag}")
            logger.info(f"  标题: {copy.title}")
            logger.info(f"  内容长度: {len(copy.content)} 字符")
            logger.info(f"  标签: {', '.join(copy.hashtags)}")
            logger.info(f"  内容预览: {copy.content[:100]}...")

            # 验证数据
            assert copy.title, "标题不能为空"
            assert len(copy.content) >= 200, f"内容长度应 >= 200, 实际: {len(copy.content)}"
            assert len(copy.hashtags) >= 3, f"标签数量应 >= 3, 实际: {len(copy.hashtags)}"
            assert all(tag.startswith('#') for tag in copy.hashtags), "所有标签必须以#开头"

        logger.success(f"\n测试1通过: 所有角度文案验证成功")

    except Exception as e:
        logger.error(f"测试1失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 测试2: 保存营销文案到数据库
    logger.info(f"\n[测试2] 保存营销文案到数据库")
    logger.info("-" * 60)

    try:
        for copy in angle_copies:
            angle_tag = copy.metadata.get("angle_tag", "default")
            post = service.save_marketing_copy(
                episode_id=episode.id,
                copy=copy,
                platform="xhs",
                angle_tag=angle_tag
            )
            logger.info(f"  保存成功: Post ID={post.id}, Angle={angle_tag}")

        # 验证数据库记录
        posts = db.query(MarketingPost).filter(
            MarketingPost.episode_id == episode.id
        ).all()

        assert len(posts) == 3, f"应该有3条记录，实际: {len(posts)}"
        logger.success(f"测试2通过: 数据库验证成功，共 {len(posts)} 条记录")

    except Exception as e:
        logger.error(f"测试2失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 测试3: 验证数据库记录与 Schema 一致性
    logger.info(f"\n[测试3] 验证数据库记录与 Schema 一致性")
    logger.info("-" * 60)

    try:
        for post in posts:
            logger.info(f"\n  Post ID: {post.id}")
            logger.info(f"    angle_tag: {post.angle_tag}")
            logger.info(f"    title: {post.title}")
            logger.info(f"    content 长度: {len(post.content)}")

            # 验证字段符合 Schema 约束
            assert 2 <= len(post.angle_tag) <= 20, f"angle_tag 长度应在 2-20"
            assert 5 <= len(post.title) <= 255, f"title 长度应在 5-255"
            assert 200 <= len(post.content) <= 8000, f"content 长度应在 200-8000"

        logger.success(f"测试3通过: 所有数据库记录符合 Schema 约束")

    except Exception as e:
        logger.error(f"测试3失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    logger.info(f"\n{'=' * 60}")
    logger.success(f"所有测试通过！")
    logger.info(f"{'=' * 60}")

    return True


if __name__ == "__main__":
    success = test_marketing_service_structured_output()
    sys.exit(0 if success else 1)
