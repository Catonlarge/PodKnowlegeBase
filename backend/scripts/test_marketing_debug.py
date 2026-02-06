"""
测试营销文案生成（带调试输出）
"""
import logging
import sys
import io
import os
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 使用测试数据库
os.environ["DATABASE_URL"] = "sqlite:///D:/programming_enviroment/EnglishPod-knowledgeBase/backend/data/episodes_test.db"

# 设置 UTF-8 编码输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 设置日志级别
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s - %(message)s')

from app.database import get_session
from app.services.marketing_service import MarketingService
from app.models import Episode

def main():
    with get_session() as db:
        episode = db.query(Episode).filter(Episode.id == 18).first()
        if episode:
            print(f"\n测试 Episode: {episode.title} (ID: {episode.id})")
            print("-" * 60)

            service = MarketingService(db)
            copies = service.generate_xiaohongshu_copy_multi_angle(episode.id)

            print(f"\n生成 {len(copies)} 个角度")
            print("=" * 60)
            for i, copy in enumerate(copies, 1):
                angle_tag = copy.metadata.get("angle_tag", "未知")
                print(f"\n角度{i}: {angle_tag}")
                print(f"  标题: {copy.title}")
                print(f"  内容长度: {len(copy.content)} 字符")
                print(f"  标签: {' '.join(copy.hashtags)}")
                print(f"  内容预览: {copy.content[:100]}...")

if __name__ == "__main__":
    main()
