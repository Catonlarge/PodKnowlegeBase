r"""
端到端测试：音频转录 -> 翻译 -> Obsidian -> 回填

使用方法：
1. 激活虚拟环境: D:\programming_enviroment\EnglishPod-knowledgeBase\backend\venv-kb\Scripts\Activate.ps1
2. 设置环境变量: $env:MOONSHOT_API_KEY="your_api_key"
3. 运行脚本: python scripts/test_end_to_end_flow.py

完整流程：
1. 从本地音频文件转录 (Whisper)
2. 批量翻译
3. 生成 Obsidian 文档
4. 解析 Obsidian 修改
5. 回填到数据库
"""
import os
import sys
from pathlib import Path

# 设置环境变量（如果未设置）
os.environ.setdefault("HF_TOKEN", os.getenv("HF_TOKEN", "dummy_token"))
os.environ.setdefault("MOONSHOT_API_KEY", os.getenv("MOONSHOT_API_KEY", ""))

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import get_session
from app.models import Episode, AudioSegment, TranscriptCue, Translation
from app.enums.workflow_status import WorkflowStatus
from app.services.whisper.whisper_service import WhisperService
from app.services.transcription_service import TranscriptionService
from app.services.translation_service import TranslationService
from app.services.obsidian_service import ObsidianService
from app.services.ai.ai_service import AIService
from app.utils.file_utils import calculate_md5_sync, get_audio_duration


def main():
    print("=" * 80)
    print("端到端测试：音频转录 -> 翻译 -> Obsidian -> 回填")
    print("=" * 80)

    # 音频文件路径
    audio_path = Path(r"D:\programming_enviroment\learning-EnglishPod3\backend\data\sample_audio\003.mp3")

    if not audio_path.exists():
        print(f"\n错误: 音频文件不存在: {audio_path}")
        return

    print(f"\n音频文件: {audio_path}")
    print(f"文件大小: {audio_path.stat().st_size / 1024 / 1024:.2f} MB")

    # 检查 API Key
    if not os.getenv("MOONSHOT_API_KEY"):
        print("\n警告: MOONSHOT_API_KEY 未设置，跳过翻译步骤")
        print("设置方法: $env:MOONSHOT_API_KEY='your_api_key'")

    with get_session() as db:
        try:
            # ========================================
            # Step 1: 创建 Episode
            # ========================================
            print("\n" + "=" * 80)
            print("Step 1: 创建 Episode")
            print("=" * 80)

            file_hash = calculate_md5_sync(str(audio_path))
            duration = get_audio_duration(str(audio_path))

            # 检查是否已存在
            existing = db.query(Episode).filter(Episode.file_hash == file_hash).first()
            if existing:
                print(f"Episode 已存在: {existing.title} (ID: {existing.id})")
                episode = existing
            else:
                episode = Episode(
                    title=f"Test Episode - {audio_path.stem}",
                    file_hash=file_hash,
                    source_url=str(audio_path),
                    duration=duration,
                    workflow_status=WorkflowStatus.INIT.value
                )
                db.add(episode)
                db.flush()
                print(f"创建 Episode: {episode.title} (ID: {episode.id})")
                print(f"  时长: {duration:.2f} 秒 ({duration/60:.1f} 分钟)")

            # ========================================
            # Step 2: 转录 (Whisper)
            # ========================================
            print("\n" + "=" * 80)
            print("Step 2: 转录音频 (Whisper)")
            print("=" * 80)

            # 加载 Whisper 模型
            print("加载 Whisper 模型...")
            WhisperService.load_models()
            whisper_service = WhisperService.get_instance()

            # 创建转录服务
            transcription_service = TranscriptionService(db, whisper_service)

            # 执行转录
            print(f"开始转录: {audio_path}")
            cues = transcription_service.transcribe_episode(
                episode_id=episode.id,
                audio_path=str(audio_path)
            )

            print(f"转录完成: {len(cues)} 条字幕")

            # 显示前 3 条
            print("\n转录结果预览（前 3 条）:")
            for cue in cues[:3]:
                print(f"  [{cue.start_time:.1f}s - {cue.end_time:.1f}s] {cue.speaker}: {cue.text}")

            # ========================================
            # Step 3: 翻译
            # ========================================
            print("\n" + "=" * 80)
            print("Step 3: 批量翻译")
            print("=" * 80)

            if os.getenv("MOONSHOT_API_KEY"):
                ai_service = AIService(provider="moonshot")
                translation_service = TranslationService(db, ai_service)

                print("开始批量翻译...")
                count = translation_service.batch_translate(episode.id, language_code="zh")
                print(f"翻译完成: {count} 条")

                # 显示前 3 条翻译
                print("\n翻译结果预览（前 3 条）:")
                translations = db.query(Translation).join(TranscriptCue).join(
                    AudioSegment
                ).filter(
                    AudioSegment.episode_id == episode.id,
                    Translation.language_code == "zh"
                ).limit(3).all()

                for t in translations:
                    cue = t.cue
                    print(f"  [{cue.start_time:.1f}s] {cue.text[:40]}...")
                    print(f"    -> {t.translation}")
            else:
                print("跳过翻译（MOONSHOT_API_KEY 未设置）")

            # ========================================
            # Step 4: 生成 Obsidian 文档
            # ========================================
            print("\n" + "=" * 80)
            print("Step 4: 生成 Obsidian 文档")
            print("=" * 80)

            obsidian_service = ObsidianService(db, vault_path=None)
            file_path = obsidian_service.save_episode(episode.id, language_code="zh")

            print(f"Obsidian 文档已生成: {file_path}")
            print(f"  文件名: {file_path.name}")

            if file_path.exists():
                print(f"  文件大小: {file_path.stat().st_size / 1024:.1f} KB")

                # 显示前 500 字符
                content = file_path.read_text(encoding='utf-8')
                print("\n文档预览（前 500 字符）:")
                print("-" * 80)
                print(content[:500])
                print("..." if len(content) > 500 else "")
                print("-" * 80)

            # ========================================
            # Step 5: 解析 Obsidian 文档
            # ========================================
            print("\n" + "=" * 80)
            print("Step 5: 解析 Obsidian 文档")
            print("=" * 80)

            # 获取原始 Markdown
            markdown = obsidian_service.render_episode(episode.id, language_code="zh")

            # 解析（应该没有差异）
            diffs = obsidian_service.parse_episode_from_markdown(
                episode.id, markdown, language_code="zh"
            )
            print(f"原始文档差异检测: {len(diffs)} 个修改")

            # ========================================
            # Step 6: 演示修改和回填
            # ========================================
            print("\n" + "=" * 80)
            print("Step 6: 演示修改和回填")
            print("=" * 80)

            if os.getenv("MOONSHOT_API_KEY"):
                # 获取第一条翻译
                first_translation = db.query(Translation).join(TranscriptCue).join(
                    AudioSegment
                ).filter(
                    AudioSegment.episode_id == episode.id,
                    Translation.language_code == "zh"
                ).first()

                if first_translation:
                    original = first_translation.translation
                    modified = f"[已修改] {original}"

                    print(f"模拟修改翻译:")
                    print(f"  原始: {original}")
                    print(f"  修改: {modified}")

                    # 修改 Markdown 并重新解析
                    modified_markdown = markdown.replace(original, modified)
                    test_diffs = obsidian_service.parse_episode_from_markdown(
                        episode.id, modified_markdown, language_code="zh"
                    )

                    print(f"\n修改后差异检测: {len(test_diffs)} 个修改")
                    if test_diffs:
                        print(f"  Cue ID: {test_diffs[0].cue_id}")
                        print(f"  原始: {test_diffs[0].original}")
                        print(f"  修改: {test_diffs[0].edited}")

                    # 回填到数据库
                    print("\n执行回填...")
                    from app.workflows.publisher import WorkflowPublisher
                    from rich.console import Console

                    publisher = WorkflowPublisher(db, Console())

                    # 临时修改文件内容以测试回填
                    file_path.write_text(modified_markdown, encoding='utf-8')
                    backfill_diffs = publisher.parse_and_backfill(episode)

                    print(f"回填完成: {len(backfill_diffs)} 个修改")

                    # 验证数据库
                    db.refresh(first_translation)
                    print(f"\n数据库验证:")
                    print(f"  翻译内容: {first_translation.translation}")
                    print(f"  是否已编辑: {first_translation.is_edited}")
                    print(f"  原始翻译: {first_translation.original_translation}")
            else:
                print("跳过回填演示（没有翻译数据）")

            # ========================================
            # Summary
            # ========================================
            print("\n" + "=" * 80)
            print("测试完成!")
            print("=" * 80)
            print(f"\nEpisode ID: {episode.id}")
            print(f"字幕数量: {len(cues)}")
            print(f"Obsidian 文档: {file_path}")
            print("\n下一步:")
            print("  1. 用 Obsidian 打开文档查看")
            print("  2. 手动修改部分翻译")
            print("  3. 重新运行 parse_and_backfill 测试回填")

        except Exception as e:
            print(f"\n错误: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
