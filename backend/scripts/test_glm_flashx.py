"""
测试 Zhipu GLM-4.7-FlashX 模型调用

验证营销服务是否能正常调用智谱 GLM-FlashX 模型
"""
import sys
import io
from pathlib import Path

# 添加 backend 目录到 Python 路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# 处理 Windows emoji 输出问题
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base
from app.services.marketing_service import MarketingService
from app.config import get_marketing_llm_config, ZHIPU_API_KEY, ZHIPU_MODEL


def test_glm_flashx_config():
    """测试配置是否正确加载"""
    print("\n" + "="*60)
    print("测试1: 配置加载")
    print("="*60)

    config = get_marketing_llm_config()
    provider = config['model'].split('-')[0] if '-' in config['model'] else config['model']
    print(f"Provider: {provider}")
    print(f"Model: {config['model']}")
    print(f"Base URL: {config['base_url']}")
    print(f"API Key: {'*** Set ***' if ZHIPU_API_KEY else 'NOT SET'}")

    print("\n配置加载测试通过!")


def test_glm_flashx_call():
    """测试 GLM-FlashX 模型调用"""
    print("\n" + "="*60)
    print("测试2: GLM-FlashX 模型调用")
    print("="*60)

    # 使用内存数据库进行测试
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    # 创建测试 Episode
    from app.models import Episode
    episode = Episode(
        title="测试播客：英语学习技巧",
        ai_summary="本集播客分享了一些实用的英语学习技巧，包括听力训练、口语练习和词汇积累方法。",
        file_hash="test_hash_12345",
        duration=180.0
    )
    db.add(episode)
    db.commit()

    print(f"\n测试 Episode: {episode.title}")
    print(f"Summary: {episode.ai_summary[:50]}...")

    # 创建 MarketingService 并测试
    service = MarketingService(db)

    print("\n正在调用 GLM-FlashX 生成标题...")
    try:
        titles = service.generate_titles(episode.id, count=3)
        print(f"\n生成的标题 ({len(titles)} 个):")
        for i, title in enumerate(titles, 1):
            print(f"  {i}. {title}")

        assert len(titles) == 3, "标题数量不正确"
        assert all(len(t) > 0 for t in titles), "存在空标题"
        print("\n标题生成测试通过!")

    except Exception as e:
        print(f"\n标题生成失败: {e}")
        import traceback
        traceback.print_exc()
        raise

    print("\n正在调用 GLM-FlashX 生成标签...")
    try:
        hashtags = service.generate_hashtags(episode.id, max_tags=5)
        print(f"\n生成的标签 ({len(hashtags)} 个):")
        print(f"  {' '.join(hashtags)}")

        assert len(hashtags) > 0, "标签为空"
        assert all(tag.startswith('#') for tag in hashtags), "标签格式错误"
        print("\n标签生成测试通过!")

    except Exception as e:
        print(f"\n标签生成失败: {e}")
        import traceback
        traceback.print_exc()
        raise

    print("\n正在调用 GLM-FlashX 生成小红书文案...")
    try:
        copy = service.generate_xiaohongshu_copy(episode.id)
        print(f"\n生成的文案:")
        print(f"  标题: {copy.title}")
        print(f"  标签: {' '.join(copy.hashtags)}")
        print(f"  内容: {copy.content[:100]}...")

        assert copy.title, "标题为空"
        assert copy.content, "内容为空"
        assert len(copy.hashtags) > 0, "标签为空"
        print("\n小红书文案生成测试通过!")

    except Exception as e:
        print(f"\n文案生成失败: {e}")
        import traceback
        traceback.print_exc()
        raise

    db.close()


def main():
    """运行所有测试"""
    try:
        test_glm_flashx_config()
        test_glm_flashx_call()

        print("\n" + "="*60)
        print("所有测试通过! GLM-FlashX 模型调用正常")
        print("="*60 + "\n")

    except Exception as e:
        print("\n" + "="*60)
        print(f"测试失败: {e}")
        print("="*60 + "\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
