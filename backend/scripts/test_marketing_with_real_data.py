"""
MarketingService 真实数据测试脚本

使用方法：
1. 激活虚拟环境: D:\programming_enviroment\EnglishPod-knowledgeBase\backend\venv-kb\Scripts\Activate.ps1
2. 运行脚本: python scripts/test_marketing_with_real_data.py

功能：
1. 从数据库获取最新的 Episode
2. 生成小红书风格营销文案
3. 保存到数据库
4. 演示完整工作流
"""
import os
import sys
from pathlib import Path

# 设置 UTF-8 编码输出（解决 Windows 终端 emoji 显示问题）
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 设置临时环境变量
os.environ.setdefault("HF_TOKEN", "dummy_token")
os.environ.setdefault("MOONSHOT_API_KEY", "dummy_key")
os.environ.setdefault("GEMINI_API_KEY", "dummy_key")
os.environ.setdefault("ZHIPU_API_KEY", "dummy_key")

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import get_session
from app.services.marketing_service import MarketingService
from app.models import Episode, MarketingPost
from app.enums.workflow_status import WorkflowStatus
from sqlalchemy import desc


def print_section(title: str):
    """打印分节标题"""
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def main():
    print_section("MarketingService 真实数据测试")

    with get_session() as db:
        # 获取最新的已翻译 Episode
        episode = db.query(Episode).filter(
            Episode.workflow_status == WorkflowStatus.TRANSLATED.value
        ).order_by(desc(Episode.id)).first()

        if not episode:
            print("\n没有找到已翻译的 Episode")
            print("请先运行翻译服务生成翻译数据")
            return

        print(f"\n找到 Episode:")
        print(f"  ID: {episode.id}")
        print(f"  标题: {episode.title}")
        print(f"  状态: {WorkflowStatus(episode.workflow_status).label}")
        print(f"  AI 摘要长度: {len(episode.ai_summary) if episode.ai_summary else 0} 字符")
        print()

        # 创建 MarketingService
        service = MarketingService(db, llm_service=None)

        # 步骤 1: 提取金句
        print_section("步骤 1: 提取金句")
        try:
            quotes = service.extract_key_quotes(episode.id, max_quotes=5)
            print(f"成功提取 {len(quotes)} 条金句:")
            for i, quote in enumerate(quotes, 1):
                preview = quote[:80] + "..." if len(quote) > 80 else quote
                print(f"  {i}. {preview}")
        except Exception as e:
            print(f"提取金句失败: {e}")
            import traceback
            traceback.print_exc()
            return

        # 步骤 2: 生成标题
        print_section("步骤 2: 生成标题")
        try:
            titles = service.generate_titles(episode.id, count=5)
            print(f"成功生成 {len(titles)} 个标题:")
            for i, title in enumerate(titles, 1):
                print(f"  {i}. {title}")
        except Exception as e:
            print(f"生成标题失败: {e}")
            import traceback
            traceback.print_exc()
            return

        # 步骤 3: 生成标签
        print_section("步骤 3: 生成话题标签")
        try:
            hashtags = service.generate_hashtags(episode.id, max_tags=10)
            print(f"成功生成 {len(hashtags)} 个标签:")
            print(f"  {' '.join(hashtags)}")
        except Exception as e:
            print(f"生成标签失败: {e}")
            import traceback
            traceback.print_exc()
            return

        # 步骤 4: 生成小红书文案
        print_section("步骤 4: 生成小红书文案")
        try:
            marketing_copy = service.generate_xiaohongshu_copy(episode.id)
            print(f"文案生成成功!")
            print(f"\n标题:")
            print(f"  {marketing_copy.title}")
            print(f"\n正文:")
            print("-" * 70)
            print(marketing_copy.content)
            print("-" * 70)
            print(f"\n标签:")
            print(f"  {' '.join(marketing_copy.hashtags)}")
            print(f"\n金句 ({len(marketing_copy.key_quotes)} 条):")
            for i, quote in enumerate(marketing_copy.key_quotes, 1):
                preview = quote[:60] + "..." if len(quote) > 60 else quote
                print(f"  {i}. {preview}")
        except Exception as e:
            print(f"生成文案失败: {e}")
            import traceback
            traceback.print_exc()
            return

        # 步骤 5: 保存到数据库
        print_section("步骤 5: 保存到数据库")
        try:
            post = service.save_marketing_copy(
                episode_id=episode.id,
                copy=marketing_copy,
                platform="xhs",
                angle_tag="AI干货向"
            )
            print(f"文案已保存到数据库:")
            print(f"  文案 ID: {post.id}")
            print(f"  Episode ID: {post.episode_id}")
            print(f"  平台: {post.platform}")
            print(f"  角度标签: {post.angle_tag}")
            print(f"  状态: {post.status}")
            print(f"  创建时间: {post.created_at}")
        except Exception as e:
            print(f"保存失败: {e}")
            import traceback
            traceback.print_exc()
            return

        # 步骤 6: 演示多角度文案生成
        print_section("步骤 6: 演示多角度文案生成")

        angles = ["轻松有趣向", "深度思考向", "实用干货向"]
        print(f"\n为同一 Episode 生成 {len(angles)} 个不同角度的文案:")

        for angle in angles:
            try:
                copy = service.generate_xiaohongshu_copy(episode.id)
                post = service.save_marketing_copy(
                    episode_id=episode.id,
                    copy=copy,
                    platform="xhs",
                    angle_tag=angle
                )
                print(f"  ✓ [{angle}] 文案 ID: {post.id}")
            except Exception as e:
                print(f"  ✗ [{angle}] 生成失败: {e}")

        # 验证数据库中的记录数
        count = db.query(MarketingPost).filter(
            MarketingPost.episode_id == episode.id
        ).count()
        print(f"\n数据库中该 Episode 的营销文案总数: {count}")

        # 总结
        print_section("测试完成!")
        print(f"\n提示:")
        print(f"  1. 查看 MarketingPost 表中的记录")
        print(f"  2. 可以查询 episode_id={episode.id} 的所有文案")
        print(f"  3. 每个文案可以有不同的 angle_tag (角度标签)")
        print(f"\n数据库查询示例:")
        print(f'  db.query(MarketingPost).filter(MarketingPost.episode_id == {episode.id}).all()')


if __name__ == "__main__":
    main()
