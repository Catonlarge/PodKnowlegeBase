"""
MarketingService 真实 AI 服务测试脚本

使用方法：
1. 激活虚拟环境: D:\programming_enviroment\EnglishPod-knowledgeBase\backend\venv-kb\Scripts\Activate.ps1
2. 运行脚本: python scripts/test_marketing_real_ai.py <文件路径>

功能：
1. 读取指定的文本文件
2. 使用真实 AI 服务生成小红书营销文案
3. 展示生成结果
"""
import os
import sys
from pathlib import Path

# 设置 UTF-8 编码输出（解决 Windows 终端 emoji 显示问题）
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 设置必需的环境变量（用于测试）
os.environ.setdefault("HF_TOKEN", "dummy_token")
os.environ.setdefault("MOONSHOT_API_KEY", os.environ.get("MOONSHOT_API_KEY", "dummy_key"))
os.environ.setdefault("GEMINI_API_KEY", "dummy_key")
os.environ.setdefault("ZHIPU_API_KEY", "dummy_key")

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import get_session
from app.services.marketing_service import MarketingService
from app.models import Episode
from sqlalchemy import desc


def print_section(title: str):
    """打印分节标题"""
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def main():
    if len(sys.argv) < 2:
        print("用法: python scripts/test_marketing_real_ai.py <文本文件路径>")
        print("\n示例:")
        print("  python scripts/test_marketing_real_ai.py D:\\\\path\\\\to\\\\017_fulltext.txt")
        return

    file_path = sys.argv[1]

    # 读取文件内容
    print_section("步骤 1: 读取文件内容")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        print(f"文件: {file_path}")
        print(f"内容长度: {len(content)} 字符")
        print(f"预览前 200 字:")
        print("-" * 70)
        print(content[:200])
        print("..." if len(content) > 200 else "")
        print("-" * 70)
    except Exception as e:
        print(f"读取文件失败: {e}")
        return

    # 从文件名提取标题
    file_name = Path(file_path).stem
    title = f"{file_name.replace('_', ' ').replace('-', ' ')}"

    # 创建临时 Episode 用于测试
    print_section("步骤 2: 创建测试 Episode")

    with get_session() as db:
        # 检查是否已有相同 file_hash 的 Episode
        existing_episode = db.query(Episode).filter(
            Episode.file_hash == f"test_{file_name}"
        ).first()

        if existing_episode:
            episode = existing_episode
            print(f"使用已存在的 Episode: {episode.id}")
        else:
            episode = Episode(
                title=title,
                file_hash=f"test_{file_name}",
                duration=300.0,
                source_url=f"file://{file_path}",
                ai_summary=content[:2000] if len(content) > 2000 else content,  # 限制摘要长度
                workflow_status=5  # TRANSLATED 状态
            )
            db.add(episode)
            db.flush()
            print(f"创建新 Episode: {episode.id}")

        # 创建 MarketingService
        print_section("步骤 3: 初始化 AI 服务")
        service = MarketingService(db, llm_service=None)

        # 检查 AI 服务配置
        from app.config import MOONSHOT_API_KEY, MOONSHOT_MODEL
        if MOONSHOT_API_KEY and MOONSHOT_API_KEY != "your_api_key_here":
            print(f"AI 服务已配置")
            print(f"  提供商: Moonshot")
            print(f"  模型: {MOONSHOT_MODEL}")
        else:
            print(f"警告: AI 服务未配置，将使用模拟数据")
            print(f"  请在 .env 文件中设置 MOONSHOT_API_KEY")

        # 生成营销文案
        print_section("步骤 4: 生成小红书营销文案（使用真实 AI）")

        try:
            marketing_copy = service.generate_xiaohongshu_copy(episode.id)
            print(f"\n✅ 文案生成成功!")
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
                preview = quote[:80] + "..." if len(quote) > 80 else quote
                print(f"  {i}. {preview}")

            # 保存到数据库
            print_section("步骤 5: 保存到数据库")
            post = service.save_marketing_copy(
                episode_id=episode.id,
                copy=marketing_copy,
                platform="xhs",
                angle_tag="AI生成测试"
            )
            print(f"文案已保存到数据库:")
            print(f"  文案 ID: {post.id}")
            print(f"  Episode ID: {post.episode_id}")
            print(f"  角度标签: {post.angle_tag}")
            print(f"  状态: {post.status}")

        except Exception as e:
            print(f"生成文案失败: {e}")
            import traceback
            traceback.print_exc()
            return

        # 生成多个角度
        print_section("步骤 6: 生成多角度文案")

        angles = ["干货硬核向", "轻松有趣向", "深度思考向"]
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

        # 总结
        print_section("测试完成!")
        print(f"\n提示:")
        print(f"  1. 查看 MarketingPost 表中的记录")
        print(f"  2. 可以查询 episode_id={episode.id} 的所有文案")
        print(f"  3. 每个文案可以有不同的 angle_tag (角度标签)")


if __name__ == "__main__":
    main()
