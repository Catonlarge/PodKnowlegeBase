"""
ObsidianService 真实数据测试脚本

使用方法：
1. 激活虚拟环境: D:\programming_enviroment\EnglishPod-knowledgeBase\backend\venv-kb\Scripts\Activate.ps1
2. 运行脚本: python scripts/test_obsidian_with_real_data.py

功能：
1. 从数据库获取最新的 Episode
2. 生成 Obsidian Markdown 文档
3. 保存到 Obsidian Vault
4. 演示解析和回填功能
"""
import os
import sys
from pathlib import Path

# 设置临时环境变量
os.environ.setdefault("HF_TOKEN", "dummy_token")
os.environ.setdefault("MOONSHOT_API_KEY", "dummy_key")
os.environ.setdefault("GEMINI_API_KEY", "dummy_key")
os.environ.setdefault("ZHIPU_API_KEY", "dummy_key")

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import get_session
from app.services.obsidian_service import ObsidianService
from app.models import Episode, Translation, TranscriptCue, AudioSegment, Chapter
from app.enums.workflow_status import WorkflowStatus
from app.enums.translation_status import TranslationStatus
from sqlalchemy import desc


def main():
    print("=" * 70)
    print("ObsidianService 真实数据测试")
    print("=" * 70)

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
        print()

        # 检查翻译数量
        translation_count = db.query(Translation).filter(
            Translation.language_code == "zh",
            Translation.translation_status == TranslationStatus.COMPLETED.value
        ).join(
            TranscriptCue, Translation.cue_id == TranscriptCue.id
        ).join(
            AudioSegment, TranscriptCue.segment_id == AudioSegment.id
        ).filter(
            AudioSegment.episode_id == episode.id
        ).count()

        print(f"中文翻译数量: {translation_count}")

        if translation_count == 0:
            print("\n没有找到翻译数据，跳过测试")
            return

        # 创建 ObsidianService
        print("\n" + "-" * 70)
        print("步骤 1: 渲染 Markdown 文档")
        print("-" * 70)

        service = ObsidianService(db, vault_path=None)  # 使用配置中的路径

        try:
            markdown = service.render_episode(episode.id, language_code="zh")
            print(f"Markdown 生成成功!")
            print(f"  总长度: {len(markdown)} 字符")

            # 显示前 500 字符
            print("\n前 500 字符预览:")
            print("-" * 70)
            print(markdown[:500])
            print("..." if len(markdown) > 500 else "")
            print("-" * 70)

        except Exception as e:
            print(f"渲染失败: {e}")
            import traceback
            traceback.print_exc()
            return

        # 保存到文件
        print("\n" + "-" * 70)
        print("步骤 2: 保存到 Obsidian Vault")
        print("-" * 70)

        try:
            file_path = service.save_episode(episode.id, language_code="zh")
            print(f"文件已保存: {file_path}")
            print(f"  文件名: {file_path.name}")
            print(f"  目录: {file_path.parent}")

            # 验证文件存在
            if file_path.exists():
                print(f"  文件大小: {file_path.stat().st_size / 1024:.1f} KB")
                print("  文件验证: 成功")
            else:
                print("  警告: 文件不存在")

        except Exception as e:
            print(f"保存失败: {e}")
            import traceback
            traceback.print_exc()
            return

        # 演示解析功能
        print("\n" + "-" * 70)
        print("步骤 3: 演示解析功能（检测修改）")
        print("-" * 70)

        try:
            # 解析原始 Markdown（应该没有差异）
            diffs = service.parse_episode_from_markdown(
                episode.id,
                markdown,
                language_code="zh"
            )
            print(f"原始 Markdown 差异检测: {len(diffs)} 个修改")

            # 模拟用户修改
            print("\n模拟用户修改翻译...")
            # 读取第一个翻译
            first_cue = db.query(TranscriptCue).join(
                AudioSegment, TranscriptCue.segment_id == AudioSegment.id
            ).filter(
                AudioSegment.episode_id == episode.id
            ).first()

            if first_cue:
                first_translation = db.query(Translation).filter(
                    Translation.cue_id == first_cue.id,
                    Translation.language_code == "zh"
                ).first()

                if first_translation:
                    original = first_translation.translation
                    modified = f"[已修改] {original}"

                    print(f"  原始翻译: {original}")
                    print(f"  修改后: {modified}")

                    # 替换并检测
                    modified_markdown = markdown.replace(original, modified)
                    test_diffs = service.parse_episode_from_markdown(
                        episode.id,
                        modified_markdown,
                        language_code="zh"
                    )

                    print(f"\n修改后差异检测: {len(test_diffs)} 个修改")
                    if test_diffs:
                        print(f"  Cue ID: {test_diffs[0].cue_id}")
                        print(f"  原始: {test_diffs[0].original}")
                        print(f"  修改: {test_diffs[0].edited}")

        except Exception as e:
            print(f"解析演示失败: {e}")
            import traceback
            traceback.print_exc()

        print("\n" + "=" * 70)
        print("测试完成!")
        print("=" * 70)
        print(f"\n生成的文件: {file_path}")
        print(f"可以用 Obsidian 或文本编辑器打开查看")
        print("\n提示:")
        print("  1. 打开 Obsidian Vault 查看生成的 Markdown 文件")
        print("  2. 尝试修改中文翻译")
        print("  3. 使用 parse_episode_from_markdown() 检测修改")
        print("  4. 使用 parse_and_backfill_from_markdown() 回填到数据库")


if __name__ == "__main__":
    main()
