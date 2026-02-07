"""
发布 Episode 到 Notion

发布指定 Episode 到 Notion 工作区

使用方法:
    python scripts/publish_episode_to_notion.py <episode_id>

示例:
    python scripts/publish_episode_to_notion.py 19
"""
import io
import sys
import argparse
from pathlib import Path

# Windows UTF-8 编码处理
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.database import get_session
from app.models import Episode
from app.services.publishers.notion import NotionPublisher


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="发布 Episode 到 Notion")
    parser.add_argument("episode_id", type=int, help="Episode ID")
    args = parser.parse_args()

    print("=" * 60)
    print("发布 Episode 到 Notion")
    print("=" * 60)

    with get_session() as db:
        try:
            # 获取 Episode
            episode = db.get(Episode, args.episode_id)
            if not episode:
                print(f"\n错误: Episode {args.episode_id} 不存在")
                return 1

            print(f"\n正在发布 Episode {args.episode_id} 到 Notion...")
            print(f"  标题: {episode.title}")
            print(f"  状态: {episode.workflow_status}")

            # 创建 NotionPublisher
            publisher = NotionPublisher(db=db)

            # 验证配置
            if not publisher.validate_config():
                print("\n错误: Notion API 配置无效")
                print("请检查 NOTION_API_KEY 环境变量是否已设置")
                return 1

            # 发布 Episode
            result = publisher.publish_episode(episode)

            if result.status == "success":
                print(f"\n发布成功！")
                print(f"  Episode ID: {result.episode_id}")
                print(f"  Notion Page ID: {result.platform_record_id}")
                clean_page_id = result.platform_record_id.replace('-', '')
                print(f"  Notion URL: https://www.notion.so/{clean_page_id}")
                return 0
            else:
                print(f"\n发布失败: {result.error_message}")
                return 1

        except Exception as e:
            print(f"\n错误: {e}")
            import traceback
            traceback.print_exc()
            return 1


if __name__ == "__main__":
    sys.exit(main())
