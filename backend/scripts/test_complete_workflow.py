#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
完整工作流测试：从本地音频文件到发布（跳过 URL 下载）

完整流程：
1. 创建 Episode (从本地音频文件)
2. WhisperX 转录
3. LLM 字幕校对
4. 语义章节切分
5. 批量翻译
6. 生成 Obsidian 文档
7. 生成营销文案
8. 演示解析和回填

使用方法：
1. 激活虚拟环境:
   D:\programming_enviroment\EnglishPod-knowledgeBase\backend\venv-kb\Scripts\Activate.ps1

2. 运行脚本:
   python scripts/test_complete_workflow.py <音频文件路径>

示例:
   python scripts/test_complete_workflow.py "D:\audio\test.mp3"
   python scripts/test_complete_workflow.py "D:\audio\test.mp3" --skip-proofreading
   python scripts/test_complete_workflow.py "D:\audio\test.mp3" --test-db

环境变量要求（必需）:
   - MOONSHOT_API_KEY: Moonshot Kimi API Key (主要 LLM)
   - ZHIPU_API_KEY: Zhipu GLM API Key (备用 LLM)
   - GEMINI_API_KEY: Google Gemini API Key (备用 LLM)
   - HF_TOKEN: HuggingFace Token (WhisperX 说话人分离)
"""
import os
import sys
import argparse
from pathlib import Path
from typing import Optional

# Fix encoding for Windows console
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from rich.console import Console

from app.database import get_session, _session_factory
from app.config import (
    MOONSHOT_API_KEY,
    MOONSHOT_BASE_URL,
    BASE_DIR,
)
from app.models import Episode, AudioSegment, TranscriptCue, Translation, Chapter
from app.enums.workflow_status import WorkflowStatus
from app.services.whisper.whisper_service import WhisperService
from app.services.transcription_service import TranscriptionService
from app.services.segmentation_service import SegmentationService
from app.services.translation_service import TranslationService
from app.services.obsidian_service import ObsidianService
from app.services.marketing_service import MarketingService
from app.services.subtitle_proofreading_service import SubtitleProofreadingService
from app.services.ai.ai_service import AIService
from app.utils.file_utils import calculate_md5_sync, get_audio_duration


class CompleteWorkflowTester:
    """完整工作流测试器"""

    def __init__(self, db: Session, console: Optional[Console] = None):
        """初始化测试器"""
        self.db = db
        self.console = console or Console()
        self.ai_service: Optional[AIService] = None
        self.episode: Optional[Episode] = None

    def check_environment(self) -> bool:
        """检查环境变量是否设置"""
        self.console.print()
        self.console.print("[bold cyan]环境变量检查[/bold cyan]")
        self.console.print("-" * 60)

        required_vars = {
            "MOONSHOT_API_KEY": MOONSHOT_API_KEY,
            "HF_TOKEN": os.getenv("HF_TOKEN"),
        }

        all_set = True
        for var_name, var_value in required_vars.items():
            status = "[green]OK[/green]" if var_value else "[red]MISSING[/red]"
            self.console.print(f"  {status} {var_name}")
            if not var_value:
                all_set = False

        if not all_set:
            self.console.print()
            self.console.print("[yellow]请设置缺少的环境变量后再运行[/yellow]")
            return False

        self.console.print()
        return True

    def create_episode_from_audio(self, audio_path: str) -> Episode:
        """从本地音频文件创建 Episode"""
        self.console.print()
        self.console.print("[bold cyan]Step 1: 创建 Episode[/bold cyan]")
        self.console.print("-" * 60)

        audio_file = Path(audio_path)
        if not audio_file.exists():
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        # 计算文件哈希和时长
        file_hash = calculate_md5_sync(str(audio_file))
        duration = get_audio_duration(str(audio_file))

        self.console.print(f"音频文件: {audio_file.name}")
        self.console.print(f"文件大小: {audio_file.stat().st_size / 1024 / 1024:.2f} MB")
        self.console.print(f"音频时长: {duration:.2f} 秒 ({duration/60:.1f} 分钟)")
        self.console.print(f"文件哈希: {file_hash}")

        # 检查是否已存在
        existing = self.db.query(Episode).filter(
            Episode.file_hash == file_hash
        ).first()

        if existing:
            self.console.print(f"[yellow]Episode 已存在: {existing.title} (ID: {existing.id})[/yellow]")
            self.console.print(f"当前状态: {WorkflowStatus(existing.workflow_status).name}")
            self.episode = existing
            return existing

        # 创建新 Episode
        episode = Episode(
            title=f"Test: {audio_file.stem}",
            file_hash=file_hash,
            source_url=str(audio_file),
            audio_path=str(audio_file),
            duration=duration,
            workflow_status=WorkflowStatus.INIT.value
        )
        self.db.add(episode)
        self.db.flush()

        self.console.print(f"[green]创建 Episode: {episode.title} (ID: {episode.id})[/green]")

        self.episode = episode
        return episode

    def transcribe_audio(self) -> None:
        """Step 2: 使用 WhisperX 转录音频"""
        self.console.print()
        self.console.print("[bold cyan]Step 2: WhisperX 转录[/bold cyan]")
        self.console.print("-" * 60)

        # 检查状态
        if self.episode.workflow_status >= WorkflowStatus.TRANSCRIBED.value:
            self.console.print(f"[yellow]已跳过: 当前状态 {WorkflowStatus(self.episode.workflow_status).name}[/yellow]")
            # 获取已有字幕用于预览
            cues = self.db.query(TranscriptCue).join(AudioSegment).filter(
                AudioSegment.episode_id == self.episode.id
            ).all()
            self._display_cue_preview(cues)
            return

        # 加载 Whisper 模型
        self.console.print("加载 WhisperX 模型...")
        WhisperService.load_models()
        whisper_service = WhisperService.get_instance()

        # 创建转录服务
        transcription_service = TranscriptionService(self.db, whisper_service)

        # 执行转录
        self.console.print(f"开始转录: {self.episode.audio_path}")
        with self.console.status("[bold green]转录中..."):
            transcription_service.segment_and_transcribe(
                episode_id=self.episode.id,
                enable_diarization=True
            )

        # 从数据库获取转录的字幕
        cues = self.db.query(TranscriptCue).join(AudioSegment).filter(
            AudioSegment.episode_id == self.episode.id
        ).all()

        self.console.print(f"[green]转录完成: {len(cues)} 条字幕[/green]")

        # 更新状态
        self.db.refresh(self.episode)

        # 显示预览
        self._display_cue_preview(cues)

    def proofread_subtitles(self) -> None:
        """Step 3: LLM 字幕校对"""
        self.console.print()
        self.console.print("[bold cyan]Step 3: LLM 字幕校对[/bold cyan]")
        self.console.print("-" * 60)

        # 检查状态
        if self.episode.workflow_status >= WorkflowStatus.PROOFREAD.value:
            self.console.print(f"[yellow]已跳过: 当前状态 {WorkflowStatus(self.episode.workflow_status).name}[/yellow]")
            return

        # 创建 LLM 客户端
        from openai import OpenAI
        llm_client = OpenAI(
            api_key=MOONSHOT_API_KEY,
            base_url=MOONSHOT_BASE_URL
        )

        # 创建校对服务
        service = SubtitleProofreadingService(self.db, llm_service=llm_client)

        # 执行校对
        self.console.print(f"开始字幕校对: {self.episode.title}")
        with self.console.status("[bold green]校对中..."):
            result = service.scan_and_correct(
                self.episode.id,
                apply=True
            )

        self.console.print(f"[green]校对完成: {result.corrected_count} 处修正[/green]")

        # 更新状态
        self.episode.workflow_status = WorkflowStatus.PROOFREAD.value
        self.db.commit()
        self.db.refresh(self.episode)

        # 显示修正预览
        if result.corrections:
            self.console.print("\n修正预览（前 3 条）:")
            for correction in result.corrections[:3]:
                self.console.print(f"  [{correction.cue_id}] {correction.original_text[:40]}...")
                self.console.print(f"    -> {correction.corrected_text[:40]}...")

    def segment_content(self) -> None:
        """Step 3: 语义章节切分"""
        self.console.print()
        self.console.print("[bold cyan]Step 3: 语义章节切分[/bold cyan]")
        self.console.print("-" * 60)

        # 检查状态
        if self.episode.workflow_status >= WorkflowStatus.SEGMENTED.value:
            self.console.print(f"[yellow]已跳过: 当前状态 {WorkflowStatus(self.episode.workflow_status).name}[/yellow]")
            # 显示已有章节
            chapters = self.db.query(Chapter).filter(
                Chapter.episode_id == self.episode.id
            ).all()
            self._display_chapter_preview(chapters)
            return

        # 确保 AI 服务已初始化
        if not self.ai_service:
            self.ai_service = AIService(provider="moonshot")

        # 创建章节切分服务
        service = SegmentationService(self.db, ai_service=self.ai_service)

        # 执行章节切分
        self.console.print(f"开始章节切分: {self.episode.title}")
        with self.console.status("[bold green]切分中..."):
            chapters = service.analyze_and_segment(self.episode.id)

        self.console.print(f"[green]切分完成: {len(chapters)} 个章节[/green]")

        # 更新状态
        self.db.refresh(self.episode)

        # 显示章节预览
        self._display_chapter_preview(chapters)

    def translate_content(self) -> None:
        """Step 4: 批量翻译"""
        self.console.print()
        self.console.print("[bold cyan]Step 4: 批量翻译[/bold cyan]")
        self.console.print("-" * 60)

        # 检查状态
        if self.episode.workflow_status >= WorkflowStatus.TRANSLATED.value:
            self.console.print(f"[yellow]已跳过: 当前状态 {WorkflowStatus(self.episode.workflow_status).name}[/yellow]")
            return

        # 确保 AI 服务已初始化
        if not self.ai_service:
            self.ai_service = AIService(provider="moonshot")

        # 创建翻译服务
        service = TranslationService(self.db, ai_service=self.ai_service)

        # 执行翻译
        self.console.print(f"开始批量翻译: {self.episode.title}")
        with self.console.status("[bold green]翻译中..."):
            count = service.batch_translate(self.episode.id, language_code="zh")

        self.console.print(f"[green]翻译完成: {count} 条[/green]")

        # 更新状态
        self.db.refresh(self.episode)

        # 显示翻译预览
        self._display_translation_preview()

    def generate_obsidian_doc(self) -> Path:
        """Step 5: 生成 Obsidian 文档"""
        self.console.print()
        self.console.print("[bold cyan]Step 5: 生成 Obsidian 文档[/bold cyan]")
        self.console.print("-" * 60)

        # 创建 Obsidian 服务
        service = ObsidianService(self.db)

        # 生成文档
        self.console.print(f"生成文档: {self.episode.title}")
        file_path = service.save_episode(self.episode.id, language_code="zh")

        self.console.print(f"[green]文档已生成: {file_path}[/green]")
        self.console.print(f"  文件名: {file_path.name}")
        self.console.print(f"  文件大小: {file_path.stat().st_size / 1024:.1f} KB")

        # 更新状态
        self.episode.workflow_status = WorkflowStatus.READY_FOR_REVIEW.value
        self.db.commit()
        self.db.refresh(self.episode)

        return file_path

    def demo_parse_and_backfill(self, obsidian_path: Path) -> None:
        """Step 6: 演示解析和回填"""
        self.console.print()
        self.console.print("[bold cyan]Step 6: 演示解析和回填[/bold cyan]")
        self.console.print("-" * 60)

        # 获取原始 Markdown
        service = ObsidianService(self.db)
        markdown = obsidian_path.read_text(encoding='utf-8')

        # 解析（应该没有差异）
        diffs = service.parse_episode_from_markdown(
            self.episode.id, markdown, language_code="zh"
        )
        self.console.print(f"原始文档差异检测: {len(diffs)} 个修改")

    def generate_marketing_doc(self) -> Optional[Path]:
        """Step 7: 生成营销文案（3个不同角度）"""
        self.console.print()
        self.console.print("[bold cyan]Step 7: 生成营销文案 (3个角度)[/bold cyan]")
        self.console.print("-" * 60)

        try:
            # 创建营销服务
            service = MarketingService(self.db)

            # 生成营销文案（3个不同角度）
            self.console.print(f"生成营销文案: {self.episode.title}")
            with self.console.status("[bold green]生成中..."):
                marketing_copies = service.generate_xiaohongshu_copy_multi_angle(self.episode.id)

            # 保存所有3个角度到数据库
            posts = []
            for i, copy in enumerate(marketing_copies, 1):
                angle_tag = copy.metadata.get("angle_tag", f"角度{i}")
                post = service.save_marketing_copy(
                    self.episode.id,
                    copy,
                    platform="xhs",
                    angle_tag=angle_tag
                )
                posts.append(post)
                self.console.print(f"[green]角度{i}已保存 (ID: {post.id}): {angle_tag}[/green]")
                self.console.print(f"  标题: {post.title[:50]}...")

            # 导出为 Markdown 文件（包含所有3个角度）
            from pathlib import Path
            from datetime import datetime

            export_dir = Path("D:/programming_enviroment/EnglishPod-knowledgeBase/obsidian/marketing")
            export_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = export_dir / f"{timestamp}-marketing-{self.episode.id}.md"

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"# 营销文案 - {self.episode.title}\n\n")
                f.write(f"> Episode ID: {self.episode.id}\n")
                f.write(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"> 状态: 待审核\n\n")
                f.write("---\n\n")

                # 写入所有角度版本
                for i, (copy, post) in enumerate(zip(marketing_copies, posts), 1):
                    angle_tag = copy.metadata.get("angle_tag", f"角度{i}")
                    f.write(f"## 角度{i}: {angle_tag}\n\n")
                    f.write(f"**数据库ID**: {post.id}\n\n")
                    f.write(f"**标题**\n{copy.title}\n\n")
                    f.write(f"**正文**\n{copy.content}\n\n")
                    f.write(f"**标签**\n")
                    f.write(" ".join(copy.hashtags))
                    f.write("\n\n---\n\n")

            self.console.print(f"[green]营销文案已导出: {file_path}[/green]")
            self.console.print(f"  大小: {file_path.stat().st_size / 1024:.1f} KB")
            self.console.print(f"  共 {len(marketing_copies)} 个角度版本")

            return file_path

        except Exception as e:
            self.console.print(f"[yellow]营销文案生成失败: {e}[/yellow]")
            import traceback
            self.console.print(traceback.format_exc())
            return None

    def run_complete_workflow(
        self,
        audio_path: str,
        skip_proofreading: bool = False,
        skip_marketing: bool = False
    ) -> Episode:
        """运行完整工作流"""
        # 检查环境
        if not self.check_environment():
            raise RuntimeError("环境变量未设置")

        # Step 1: 创建 Episode
        self.create_episode_from_audio(audio_path)

        # Step 2: 转录
        self.transcribe_audio()

        # Step 3: 字幕校对（可选）
        if not skip_proofreading:
            self.proofread_subtitles()
        else:
            self.console.print()
            self.console.print("[yellow]跳过字幕校对[/yellow]")

        # Step 4: 章节切分
        self.segment_content()

        # Step 5: 翻译
        self.translate_content()

        # Step 6: 生成 Obsidian 文档
        obsidian_path = self.generate_obsidian_doc()

        # Step 7: 演示解析和回填
        self.demo_parse_and_backfill(obsidian_path)

        # Step 8: 生成营销文案（可选）
        marketing_path = None
        if not skip_marketing:
            marketing_path = self.generate_marketing_doc()

        # 显示总结
        self._display_summary(obsidian_path, marketing_path)

        return self.episode

    def _display_cue_preview(self, cues: list) -> None:
        """显示字幕预览"""
        self.console.print("\n字幕预览（前 3 条）:")
        for cue in cues[:3]:
            self.console.print(f"  [{cue.start_time:.1f}s - {cue.end_time:.1f}s] {cue.speaker}: {cue.text[:60]}...")

    def _display_chapter_preview(self, chapters: list) -> None:
        """显示章节预览"""
        self.console.print("\n章节预览:")
        for i, chapter in enumerate(chapters, 1):
            minutes = int(chapter.start_time // 60)
            seconds = int(chapter.start_time % 60)
            end_minutes = int(chapter.end_time // 60)
            end_seconds = int(chapter.end_time % 60)
            self.console.print(f"  {i}. {chapter.title} [{minutes:02d}:{seconds:02d} - {end_minutes:02d}:{end_seconds:02d}]")
            self.console.print(f"     {chapter.summary[:80]}...")

    def _display_translation_preview(self) -> None:
        """显示翻译预览"""
        translations = self.db.query(Translation).join(TranscriptCue).join(
            AudioSegment
        ).filter(
            AudioSegment.episode_id == self.episode.id,
            Translation.language_code == "zh"
        ).limit(3).all()

        if translations:
            self.console.print("\n翻译预览（前 3 条）:")
            for t in translations:
                cue = t.cue
                self.console.print(f"  [{cue.start_time:.1f}s] {cue.text[:40]}...")
                self.console.print(f"    -> {t.translation[:60]}...")

    def _display_summary(self, obsidian_path: Path, marketing_path: Optional[Path] = None) -> None:
        """显示测试总结"""
        self.console.print()
        self.console.print("[bold cyan]" + "=" * 60 + "[/bold cyan]")
        self.console.print("[bold cyan]测试完成![/bold cyan]")
        self.console.print("[bold cyan]" + "=" * 60 + "[/bold cyan]")
        self.console.print()
        self.console.print(f"Episode ID: {self.episode.id}")
        self.console.print(f"标题: {self.episode.title}")
        self.console.print(f"状态: {WorkflowStatus(self.episode.workflow_status).name}")
        self.console.print()
        self.console.print(f"Obsidian 文档: {obsidian_path}")
        if marketing_path:
            self.console.print(f"营销文案: {marketing_path}")
        self.console.print()
        self.console.print("[bold]下一步:[/bold]")
        self.console.print("  1. 用 Obsidian 打开文档查看")


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        description="完整工作流测试：从本地音频文件到发布",
    )
    parser.add_argument("audio", help="音频文件路径")
    parser.add_argument("--skip-proofreading", action="store_true", help="跳过字幕校对")
    parser.add_argument("--skip-marketing", action="store_true", help="跳过营销文案生成")
    parser.add_argument("--test-db", action="store_true", help="使用测试数据库")

    args = parser.parse_args()

    console = Console()

    # 打印头部
    console.print()
    console.print("[bold cyan]EnglishPod3 Enhanced - 完整工作流测试[/bold cyan]")
    console.print(f"[dim]音频文件: {args.audio}[/dim]")
    if args.test_db:
        console.print("[yellow]数据库: 测试模式 (episodes_test.db)[/yellow]")
    console.print()

    # 如果使用测试数据库，重新初始化数据库连接
    if args.test_db:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.models.base import Base

        # 使用临时测试数据库
        test_db_path = BASE_DIR / "data" / "episodes_test.db"
        test_db_path.parent.mkdir(parents=True, exist_ok=True)

        # 创建测试数据库引擎
        test_engine = create_engine(
            f"sqlite:///{test_db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )

        # 创建新的 session factory
        global _session_factory
        _session_factory = sessionmaker(
            bind=test_engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )

        # 创建表（如果不存在）
        Base.metadata.create_all(test_engine)

        console.print(f"[green]测试数据库: {test_db_path}[/green]")
        console.print()

    # 使用上下文管理器创建数据库会话
    try:
        with get_session() as db:
            # 创建测试器
            tester = CompleteWorkflowTester(db, console)

            # 运行完整工作流
            episode = tester.run_complete_workflow(
                args.audio,
                skip_proofreading=args.skip_proofreading,
                skip_marketing=args.skip_marketing
            )

            return 0

    except KeyboardInterrupt:
        console.print()
        console.print("[yellow]已取消[/yellow]")
        return 130

    except Exception as e:
        console.print()
        console.print(f"[red]错误: {e}[/red]")
        import traceback
        console.print(traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())
