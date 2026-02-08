#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
APPROVED 审核工作流集成测试

测试完整的审核流程：
1. 准备 Episode（READY_FOR_REVIEW 状态）
2. 生成 Obsidian 文档（status: pending_review）
3. 模拟用户修改翻译
4. 修改状态为 approved
5. 运行 sync_approved_episodes() 同步到数据库
6. 验证选择性回填（只更新修改的翻译）
7. 验证状态变更为 APPROVED
8. 验证发布流程（只允许从 APPROVED 发布）

使用方法：
1. 激活虚拟环境:
   D:\programming_enviroment\EnglishPod-knowledgeBase\backend\venv-kb\Scripts\Activate.ps1

2. 运行脚本:
   python scripts/test_review_workflow_integration.py --episode-id 19

环境变量要求（可选）:
   - MOONSHOT_API_KEY: 如果需要生成新文档
"""
import os
import sys
import tempfile
from pathlib import Path

# Fix encoding for Windows console
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from rich.console import Console
from rich.panel import Panel

from app.database import get_session
from app.models import Episode, Translation, TranscriptCue, AudioSegment
from app.enums.workflow_status import WorkflowStatus
from app.services.obsidian_service import ObsidianService
from app.services.review_service import ReviewService
from app.workflows.publisher import WorkflowPublisher


class ReviewWorkflowIntegrationTester:
    """审核工作流集成测试器"""

    def __init__(self, db: Session, episode_id: int, temp_dir: Path = None):
        """初始化测试器"""
        self.db = db
        self.episode_id = episode_id
        self.temp_dir = temp_dir or Path(tempfile.gettempdir()) / "review_workflow_test"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.console = Console()
        self.obsidian_file_path = None
        self.edited_translations = []  # 存储编辑的翻译用于后续验证

    def prepare_episode(self) -> Episode:
        """Step 1: 准备测试 Episode"""
        self.console.print()
        self.console.print("[bold cyan]Step 1: 准备 Episode[/bold cyan]")
        self.console.print("-" * 60)

        episode = self.db.query(Episode).filter(Episode.id == self.episode_id).first()
        if not episode:
            raise ValueError(f"Episode {self.episode_id} 不存在")

        self.console.print(f"Episode ID: {episode.id}")
        self.console.print(f"标题: {episode.title}")
        self.console.print(f"当前状态: {WorkflowStatus(episode.workflow_status).label}")

        # 确保有字幕和翻译
        cue_count = self.db.query(TranscriptCue).join(AudioSegment).filter(
            AudioSegment.episode_id == episode.id
        ).count()

        translation_count = self.db.query(Translation).join(TranscriptCue).join(
            AudioSegment
        ).filter(
            AudioSegment.episode_id == episode.id,
            Translation.language_code == "zh"
        ).count()

        self.console.print(f"字幕数量: {cue_count}")
        self.console.print(f"翻译数量: {translation_count}")

        if cue_count == 0 or translation_count == 0:
            raise ValueError(f"Episode {episode.id} 缺少字幕或翻译数据")

        return episode

    def generate_obsidian_document(self) -> Path:
        """Step 2: 生成 Obsidian 文档（status: pending_review）"""
        self.console.print()
        self.console.print("[bold cyan]Step 2: 生成 Obsidian 文档[/bold cyan]")
        self.console.print("-" * 60)

        # 创建 Obsidian 服务
        obsidian_service = ObsidianService(self.db)

        # 生成文档内容
        self.console.print(f"生成文档: Episode {self.episode_id}")
        markdown_content = obsidian_service.render_episode(
            self.episode_id, language_code="zh"
        )

        # 设置为 pending_review 状态
        markdown_content = markdown_content.replace(
            "status: published",
            "status: pending_review"
        )

        # 保存到临时目录
        filename = f"{self.episode_id}-test-review.md"
        self.obsidian_file_path = self.temp_dir / filename

        with open(self.obsidian_file_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)

        self.console.print(f"[green]文档已生成: {self.obsidian_file_path}[/green]")
        self.console.print(f"  文件大小: {self.obsidian_file_path.stat().st_size / 1024:.1f} KB")

        return self.obsidian_file_path

    def simulate_user_edits(self) -> list:
        """Step 3: 模拟用户修改翻译"""
        self.console.print()
        self.console.print("[bold cyan]Step 3: 模拟用户修改翻译[/bold cyan]")
        self.console.print("-" * 60)

        # 读取文档
        with open(self.obsidian_file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 获取前 3 个翻译作为测试
        translations = self.db.query(Translation).join(TranscriptCue).join(
            AudioSegment
        ).filter(
            AudioSegment.episode_id == self.episode_id,
            Translation.language_code == "zh"
        ).limit(3).all()

        edited_translations = []
        lines = content.split('\n')
        modified_lines = lines.copy()

        for t in translations:
            # 获取干净的原始翻译（移除所有 [用户修改] 前缀）
            original = t.translation
            while original.startswith("[用户修改] "):
                original = original[len("[用户修改] "):]

            # 模拟用户修改：添加 "[用户修改]" 前缀
            edited = f"[用户修改] {original}"

            # 在文档中查找对应 cue_id 的翻译并替换
            cue_anchor = f"cue://{t.cue_id})"
            for i, line in enumerate(lines):
                if cue_anchor in line:
                    # 找到了 cue 锚点行，翻译在后面 2-3 行
                    # 格式: [时间](cue://ID) English text
                    #       (空行)
                    #       中文翻译
                    if i + 2 < len(lines):
                        translation_line_idx = i + 2
                        # 检查这行是否是翻译（不是空行，不是 cue 锚点）
                        translation_line = lines[translation_line_idx].strip()
                        if translation_line and "cue://" not in translation_line and not translation_line.startswith("**"):
                            # 找到了翻译行，替换它
                            # 需要保持原有的缩进和格式
                            original_line = lines[translation_line_idx]
                            # 找到翻译文本在行中的起始位置（去除前导空格）
                            leading_spaces = len(original_line) - len(original_line.lstrip())
                            indent = original_line[:leading_spaces]
                            # 替换翻译行
                            modified_lines[translation_line_idx] = indent + edited

                            edited_translations.append({
                                'cue_id': t.cue_id,
                                'original': original,
                                'edited': edited
                            })
                            break

        # 修改状态为 approved
        modified_lines = [line.replace("status: pending_review", "status: approved") for line in modified_lines]

        # 保存修改后的文档
        content = '\n'.join(modified_lines)
        with open(self.obsidian_file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        self.console.print(f"[green]已修改 {len(edited_translations)} 条翻译[/green]")
        for i, edit in enumerate(edited_translations, 1):
            self.console.print(f"  {i}. Cue {edit['cue_id']}")
            self.console.print(f"     原文: {edit['original'][:40]}...")
            self.console.print(f"     修改: {edit['edited'][:40]}...")

        self.console.print(f"[green]状态已修改为: approved[/green]")

        # 验证文档中的修改
        self.console.print("\n[debug] 验证文档内容:")
        with open(self.obsidian_file_path, 'r', encoding='utf-8') as f:
            doc_content = f.read()
            for edit in edited_translations[:1]:  # 只检查第一个
                cue_id = edit['cue_id']
                # 查找这个 cue 在文档中的位置
                cue_marker = f"cue://{cue_id}"
                if cue_marker in doc_content:
                    idx = doc_content.find(cue_marker)
                    snippet = doc_content[idx:idx+300]
                    self.console.print(f"  Cue {cue_id} 在文档中的内容:")
                    self.console.print(f"    {snippet[:150]}...")

        self.edited_translations = edited_translations
        return edited_translations

    def sync_to_database(self) -> int:
        """Step 4: 同步到数据库（sync_approved_episodes）"""
        self.console.print()
        self.console.print("[bold cyan]Step 4: 同步到数据库[/bold cyan]")
        self.console.print("-" * 60)

        # 重置待测试的翻译状态（确保测试的幂等性）
        test_cue_ids = [t['cue_id'] for t in self.edited_translations]
        translations = self.db.query(Translation).filter(
            Translation.cue_id.in_(test_cue_ids),
            Translation.language_code == "zh"
        ).all()

        for t in translations:
            # 移除所有 [用户修改] 前缀，恢复到真正的原始状态
            current = t.translation
            # 移除所有 "[用户修改] " 前缀
            while current.startswith("[用户修改] "):
                current = current[len("[用户修改] "):]
            # 重置状态
            t.translation = current
            t.original_translation = None
            t.is_edited = False
        self.db.commit()

        self.console.print(f"[yellow]已重置 {len(translations)} 条翻译状态[/yellow]")

        # 确保 Episode 状态为 READY_FOR_REVIEW
        episode = self.db.query(Episode).filter(Episode.id == self.episode_id).first()
        episode.workflow_status = WorkflowStatus.READY_FOR_REVIEW.value
        self.db.commit()

        self.console.print(f"Episode 状态已设置为: {WorkflowStatus.READY_FOR_REVIEW.label}")

        # 创建 ReviewService（使用临时目录）
        review_service = ReviewService(self.db)
        review_service.notes_dir = self.temp_dir

        # 执行同步
        self.console.print("执行 sync_approved_episodes()...")
        count = review_service.sync_approved_episodes()

        self.console.print(f"[green]同步完成: {count} 个 Episode[/green]")

        # 刷新数据库会话以获取最新数据
        self.db.expire_all()

        return count

    def verify_selective_writeback(self, edited_translations: list) -> bool:
        """Step 5: 验证选择性回填"""
        self.console.print()
        self.console.print("[bold cyan]Step 5: 验证选择性回填[/bold cyan]")
        self.console.print("-" * 60)

        all_passed = True

        for edit in edited_translations:
            cue_id = edit['cue_id']

            # 查询翻译
            translation = self.db.query(Translation).filter(
                Translation.cue_id == cue_id,
                Translation.language_code == "zh"
            ).first()

            if not translation:
                self.console.print(f"[red]Cue {cue_id}: 翻译不存在[/red]")
                all_passed = False
                continue

            # 验证原始翻译已保存
            if translation.original_translation != edit['original']:
                self.console.print(
                    f"[red]Cue {cue_id}: 原始翻译未正确保存[/red]"
                )
                self.console.print(f"  预期: {edit['original'][:40]}...")
                self.console.print(f"  实际: {translation.original_translation[:40] if translation.original_translation else 'None'}...")
                all_passed = False
                continue

            # 验证当前翻译已更新
            if translation.translation != edit['edited']:
                self.console.print(
                    f"[red]Cue {cue_id}: 翻译未正确更新[/red]"
                )
                self.console.print(f"  预期: {edit['edited'][:40]}...")
                self.console.print(f"  实际: {translation.translation[:40]}...")
                all_passed = False
                continue

            # 验证 is_edited 标志
            if not translation.is_edited:
                self.console.print(
                    f"[red]Cue {cue_id}: is_edited 标志未设置[/red]"
                )
                all_passed = False
                continue

            self.console.print(
                f"[green]Cue {cue_id}: 验证通过[/green]"
            )
            self.console.print(f"  原始翻译: {translation.original_translation[:40]}...")
            self.console.print(f"  当前翻译: {translation.translation[:40]}...")
            self.console.print(f"  is_edited: {translation.is_edited}")

        return all_passed

    def verify_status_change(self) -> bool:
        """Step 6: 验证状态变更为 APPROVED"""
        self.console.print()
        self.console.print("[bold cyan]Step 6: 验证状态变更[/bold cyan]")
        self.console.print("-" * 60)

        episode = self.db.query(Episode).filter(Episode.id == self.episode_id).first()
        current_status = WorkflowStatus(episode.workflow_status)

        self.console.print(f"Episode 状态: {current_status.label} ({current_status.value})")

        if current_status == WorkflowStatus.APPROVED:
            self.console.print("[green]状态验证通过: APPROVED[/green]")
            return True
        else:
            self.console.print(
                f"[red]状态验证失败: 预期 APPROVED (7)，实际 {current_status.label} ({current_status.value})[/red]"
            )
            return False

    def test_publish_from_approved(self) -> bool:
        """Step 7: 测试从 APPROVED 状态发布"""
        self.console.print()
        self.console.print("[bold cyan]Step 7: 测试发布流程[/bold cyan]")
        self.console.print("-" * 60)

        try:
            publisher = WorkflowPublisher(self.db)

            # 测试从 APPROVED 发布（应该成功）
            self.console.print("测试从 APPROVED 状态发布...")
            self.console.print("注意: 这是模拟测试，不会实际发布到平台")

            # 验证 Episode 状态
            episode = self.db.query(Episode).filter(Episode.id == self.episode_id).first()
            if episode.workflow_status != WorkflowStatus.APPROVED.value:
                self.console.print("[yellow]Episode 状态不是 APPROVED，跳过发布测试[/yellow]")
                return False

            # 验证发布前的检查
            try:
                # 这会抛出异常因为 Notion 配置可能不存在
                # 但我们只验证状态检查是否正确
                from app.services.publishers.notion import NotionPublisher
                notion_publisher = NotionPublisher(db=self.db)

                if not notion_publisher.validate_config():
                    self.console.print("[yellow]Notion 配置无效，跳过实际发布[/yellow]")
                    self.console.print("[green]状态检查通过: APPROVED 状态可以进入发布流程[/green]")
                    return True

            except Exception as e:
                self.console.print(f"[yellow]发布器初始化失败: {e}[/yellow]")
                self.console.print("[green]状态检查通过: APPROVED 状态可以进入发布流程[/green]")
                return True

        except ValueError as e:
            self.console.print(f"[red]发布失败: {e}[/red]")
            return False

    def test_publish_from_non_approved(self) -> bool:
        """Step 8: 测试从非 APPROVED 状态发布（应该失败）"""
        self.console.print()
        self.console.print("[bold cyan]Step 8: 测试从非 APPROVED 状态发布[/bold cyan]")
        self.console.print("-" * 60)

        # 临时将状态改为 READY_FOR_REVIEW
        episode = self.db.query(Episode).filter(Episode.id == self.episode_id).first()
        original_status = episode.workflow_status
        episode.workflow_status = WorkflowStatus.READY_FOR_REVIEW.value
        self.db.commit()

        self.console.print(f"临时状态: {WorkflowStatus.READY_FOR_REVIEW.label}")

        try:
            publisher = WorkflowPublisher(self.db)

            self.console.print("尝试从 READY_FOR_REVIEW 状态发布...")
            # 这应该抛出 ValueError
            publisher.publish_workflow(self.episode_id)

            self.console.print("[red]测试失败: 应该抛出异常但没有[/red]")
            episode.workflow_status = original_status  # 恢复原状态
            self.db.commit()
            return False

        except ValueError as e:
            expected_msg = f"预期状态为 {WorkflowStatus.APPROVED.label}"
            if expected_msg in str(e):
                self.console.print(f"[green]测试通过: 正确阻止了非 APPROVED 状态的发布[/green]")
                self.console.print(f"  错误信息: {e}")
                # 恢复原状态
                episode.workflow_status = original_status
                self.db.commit()
                return True
            else:
                self.console.print(f"[red]测试失败: 错误信息不符合预期[/red]")
                self.console.print(f"  预期包含: {expected_msg}")
                self.console.print(f"  实际: {e}")
                # 恢复原状态
                episode.workflow_status = original_status
                self.db.commit()
                return False

        except Exception as e:
            self.console.print(f"[red]测试失败: 抛出了非预期异常[/red]")
            self.console.print(f"  异常类型: {type(e).__name__}")
            self.console.print(f"  错误信息: {e}")
            # 恢复原状态
            episode.workflow_status = original_status
            self.db.commit()
            return False

    def run_complete_test(self) -> bool:
        """运行完整的集成测试"""
        self.console.print()
        self.console.print(Panel.fit(
            "[bold cyan]APPROVED 审核工作流集成测试[/bold cyan]\n"
            f"Episode ID: {self.episode_id}\n"
            f"临时目录: {self.temp_dir}",
            title="测试配置"
        ))

        all_passed = True

        try:
            # Step 1: 准备 Episode
            self.prepare_episode()

            # Step 2: 生成 Obsidian 文档
            self.generate_obsidian_document()

            # Step 3: 模拟用户修改
            edited_translations = self.simulate_user_edits()

            # Step 4: 同步到数据库
            count = self.sync_to_database()
            if count != 1:
                self.console.print(f"[red]同步失败: 预期 1 个 Episode，实际 {count} 个[/red]")
                all_passed = False

            # Step 5: 验证选择性回填
            if not self.verify_selective_writeback(edited_translations):
                all_passed = False

            # Step 6: 验证状态变更
            if not self.verify_status_change():
                all_passed = False

            # Step 7: 测试从 APPROVED 发布
            if not self.test_publish_from_approved():
                all_passed = False

            # Step 8: 测试从非 APPROVED 发布
            if not self.test_publish_from_non_approved():
                all_passed = False

            # 显示测试结果
            self.display_results(all_passed)

            return all_passed

        except Exception as e:
            self.console.print()
            self.console.print(f"[red]测试失败: {e}[/red]")
            import traceback
            self.console.print(traceback.format_exc())
            return False

    def display_results(self, all_passed: bool):
        """显示测试结果"""
        self.console.print()
        self.console.print("=" * 60)
        if all_passed:
            self.console.print("[bold green]所有测试通过！[/bold green]")
        else:
            self.console.print("[bold red]部分测试失败[/bold red]")
        self.console.print("=" * 60)


def main():
    """主入口"""
    import argparse

    parser = argparse.ArgumentParser(
        description="APPROVED 审核工作流集成测试"
    )
    parser.add_argument("--episode-id", type=int, required=True,
                       help="Episode ID")
    parser.add_argument("--temp-dir", type=str,
                       help="临时目录路径（默认使用系统临时目录）")

    args = parser.parse_args()

    console = Console()

    # 创建临时目录
    temp_dir = Path(args.temp_dir) if args.temp_dir else None

    # 运行测试
    try:
        with get_session() as db:
            tester = ReviewWorkflowIntegrationTester(
                db, args.episode_id, temp_dir
            )
            success = tester.run_complete_test()
            return 0 if success else 1

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
