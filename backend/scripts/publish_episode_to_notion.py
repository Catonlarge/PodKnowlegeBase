"""
发布 Episode 到 Notion

发布 Episode ID=1 到 Notion 工作区
"""
import io
import sys
from pathlib import Path

# Windows UTF-8 编码处理
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Episode
from app.services.publishers.notion import NotionPublisher


def main():
    """主函数"""
    print("=" * 60)
    print("发布 Episode 到 Notion")
    print("=" * 60)

    # 使用测试数据库（有完整数据）
    test_db_path = "D:/programming_enviroment/EnglishPod-knowledgeBase/backend/data/test_integration.db"

    # 创建数据库连接
    engine = create_engine(f"sqlite:///{test_db_path}")
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Episode ID
        episode_id = 1

        # 获取 Episode
        episode = db.get(Episode, episode_id)
        if not episode:
            print(f"\n错误: Episode {episode_id} 不存在")
            return

        print(f"\n正在发布 Episode {episode_id} 到 Notion...")
        print(f"  标题: {episode.title}")

        # 创建 NotionPublisher
        publisher = NotionPublisher(db=db)

        # 发布 Episode
        result = publisher.publish_episode(episode)

        if result.status == "success":
            print(f"\n发布成功！")
            print(f"  Episode ID: {result.episode_id}")
            print(f"  Notion Page ID: {result.platform_record_id}")
            clean_page_id = result.platform_record_id.replace('-', '')
            print(f"  Notion URL: https://www.notion.so/{clean_page_id}")
        else:
            print(f"\n发布失败: {result.error_message}")

    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()

    finally:
        db.close()


if __name__ == "__main__":
    main()
