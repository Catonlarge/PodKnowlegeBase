"""
Publish Workflow Orchestrator

Parses Obsidian document edits and publishes to multiple platforms.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from sqlalchemy.orm import Session
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from app.enums.workflow_status import WorkflowStatus
from app.models import Episode, Translation, MarketingPost, PublicationRecord
from app.services.obsidian_service import ObsidianService
from app.services.marketing_service import MarketingService
from app.services.publishers.notion import NotionPublisher
from app.services.publishers.feishu import FeishuPublisher
from app.services.publishers.ima import ImaPublisher
from app.services.publishers.marketing import MarketingPublisher
from app.config import MOONSHOT_API_KEY, MOONSHOT_BASE_URL
from openai import OpenAI


@dataclass
class Diff:
    """Represents a difference between database and Obsidian document"""
    cue_id: int
    field: str  # 'text' | 'translation'
    original_value: str
    new_value: str


class WorkflowPublisher:
    """
    Publish workflow orchestrator.

    Handles:
    1. Parsing Obsidian document for user edits
    2. Backfilling edits to database
    3. Generating marketing content
    4. Publishing to multiple platforms
    """

    def __init__(self, db: Session, console: Optional[Console] = None):
        """
        Initialize publisher.

        Args:
            db: Database session
            console: Rich Console for output
        """
        self.db = db
        self.console = console or Console()
        self.obsidian_service = ObsidianService(db)

        # Initialize marketing service (it manages its own LLM client)
        try:
            self.marketing_service = MarketingService(db)
        except Exception as e:
            self.console.print(f"  [yellow]警告: MarketingService 初始化失败: {e}[/yellow]")
            self.marketing_service = None

        # Initialize platform publishers
        self.publishers = {}

        # NotionPublisher 需要数据库会话
        try:
            self.publishers["notion"] = NotionPublisher(db)
        except (ValueError, ImportError) as e:
            self.console.print(f"  [yellow]警告: Notion 发布器初始化失败: {e}[/yellow]")
            self.console.print("  [yellow]  跳过 Notion 发布（需要配置 NOTION_API_KEY）[/yellow]")

        # 其他发布器（Stub 实现）
        self.publishers["feishu"] = FeishuPublisher()
        self.publishers["ima"] = ImaPublisher()
        self.publishers["marketing"] = MarketingPublisher()

    def publish_workflow(
        self,
        episode_id: int,
        language_code: str = "zh",
        force_remarketing: bool = False,
    ) -> Episode:
        """
        Execute the complete publish workflow.

        Args:
            episode_id: Episode ID
            language_code: 翻译语言代码，默认 "zh"
            force_remarketing: 若为 True，先删除旧营销文案再重新生成

        Returns:
            Updated Episode with PUBLISHED status

        Raises:
            ValueError: Episode not found or not ready for review
        """
        episode = self.db.get(Episode, episode_id)
        if not episode:
            raise ValueError(f"Episode not found: id={episode_id}")

        # 只允许从 APPROVED 状态发布；若为 READY_FOR_REVIEW 则先尝试同步 Obsidian 审核状态
        if episode.workflow_status != WorkflowStatus.APPROVED.value:
            if episode.workflow_status == WorkflowStatus.READY_FOR_REVIEW.value:
                self.console.print("[yellow]检测到待审核状态，先同步 Obsidian 审核状态...[/yellow]")
                from app.services.review_service import ReviewService
                review_service = ReviewService(self.db)
                count = review_service.sync_approved_episodes()
                self.db.refresh(episode)
                if count > 0:
                    self.console.print(f"[green]已同步 {count} 个已审核 Episode[/green]")

            if episode.workflow_status != WorkflowStatus.APPROVED.value:
                current_status = WorkflowStatus(episode.workflow_status)
                raise ValueError(
                    f"Episode 状态为 {current_status.label}，"
                    f"预期状态为 {WorkflowStatus.APPROVED.label}。"
                    f"请先在 Obsidian 中将 status 改为 approved 后重试，或运行 sync_review_status.py"
                )

        # Step 1: Generate marketing content
        self.console.print("[cyan]步骤 1/3: 生成营销文案...[/cyan]")
        posts = self.generate_marketing(episode, force_remarketing=force_remarketing)

        if posts:
            self.console.print(f"  生成 {len(posts)} 条营销文案")
            self._display_marketing_summary(posts)

            # 导出到 Obsidian 供审核（参考 test_complete_workflow）
            self.console.print("[cyan]步骤 2/3: 导出营销文案到 Obsidian...[/cyan]")
            from app.services.obsidian_service import ObsidianService
            obsidian_service = ObsidianService(self.db)
            try:
                marketing_path = obsidian_service.save_marketing_posts(episode.id)
                if marketing_path:
                    self.console.print(f"  [green]已导出: {marketing_path}[/green]")
                else:
                    self.console.print("  [yellow]无营销文案可导出[/yellow]")
            except Exception as e:
                self.console.print(f"  [yellow]导出失败: {e}[/yellow]")
        else:
            self.console.print("  未生成营销文案")

        # Step 3: Distribute to platforms
        self.console.print("[cyan]步骤 3/3: 分发到各平台...[/cyan]")
        records = self.distribute_to_platforms(episode, posts)

        self._display_publication_summary(records)

        # Update episode status
        episode.workflow_status = WorkflowStatus.PUBLISHED.value
        self.db.commit()

        return episode

    def parse_and_backfill(self, episode: Episode, language_code: str = "zh") -> List[Diff]:
        """
        解析 Obsidian 文档并回填编辑到数据库（独立工具方法）

        注意：此方法不应在 publish_workflow() 中调用。
        sync_approved_episodes() 已经处理了文档解析和翻译更新。
        保留此方法用于：
        - 独立测试和调试
        - 直接测试 Obsidian 文档解析功能
        - 其他需要单独回填的场景

        Args:
            episode: Episode to process
            language_code: 翻译语言代码，默认 "zh"

        Returns:
            List of Diff objects representing changes
        """
        diffs = []

        # Get Obsidian file path for this episode
        obsidian_path = self.obsidian_service._get_episode_path(episode.id)
        if not obsidian_path.exists():
            self.console.print(f"  [yellow]警告: Obsidian 文档不存在: {obsidian_path}[/yellow]")
            return diffs

        # Read the markdown file
        with open(obsidian_path, 'r', encoding='utf-8') as f:
            markdown = f.read()

        # Parse the document for changes
        diff_results = self.obsidian_service.parse_episode_from_markdown(
            episode.id, markdown, language_code=language_code
        )

        # Backfill translation changes
        for diff_result in diff_results:
            if diff_result.is_edited:
                translation = self.db.query(Translation).filter(
                    Translation.cue_id == diff_result.cue_id,
                    Translation.language_code == language_code
                ).first()

                if translation:
                    diffs.append(Diff(
                        cue_id=diff_result.cue_id,
                        field="translation",
                        original_value=diff_result.original,
                        new_value=diff_result.edited
                    ))

                    # 保存原始翻译（如果还没有保存）
                    if translation.original_translation is None:
                        translation.original_translation = translation.translation

                    # Update translation
                    translation.translation = diff_result.edited
                    translation.is_edited = True
                    self.db.add(translation)

        self.db.commit()
        return diffs

    def generate_marketing(self, episode: Episode, force_remarketing: bool = False) -> List[MarketingPost]:
        """
        Generate marketing content for episode.

        Args:
            episode: Episode to process
            force_remarketing: 若为 True，先删除该 episode 已有营销文案再重新生成

        Returns:
            List of MarketingPost objects
        """
        if not self.marketing_service:
            self.console.print("  [yellow]警告: 未配置 LLM，跳过营销文案生成[/yellow]")
            return []

        existing_posts = (
            self.db.query(MarketingPost)
            .filter(MarketingPost.episode_id == episode.id)
            .all()
        )
        if not force_remarketing and existing_posts:
            self.console.print(f"  [dim]已跳过: 该 Episode 已有 {len(existing_posts)} 条营销文案[/dim]")
            return existing_posts

        if force_remarketing:
            deleted = self.marketing_service.delete_marketing_posts_for_episode(episode.id)
            self.console.print(f"  [yellow]强制重新生成: 已清除 {deleted} 条旧营销文案[/yellow]")

        copies = self.marketing_service.generate_xiaohongshu_copy_multi_angle(episode.id)

        # Save each copy as a MarketingPost
        posts = []
        for i, copy in enumerate(copies):
            angle_tag = copy.metadata.get("angle_tag", copy.metadata.get("angle_name", f"angle_{i+1}"))
            post = self.marketing_service.save_marketing_copy(
                episode.id, copy, platform="xhs", angle_tag=angle_tag
            )
            posts.append(post)

        return posts

    def export_marketing_only(
        self,
        episode_id: int,
        force_remarketing: bool = False,
    ) -> Optional[Path]:
        """
        仅生成并导出营销文案到 Obsidian，不发布到任何平台。

        Args:
            episode_id: Episode ID
            force_remarketing: 若为 True，先删除旧文案再重新生成

        Returns:
            Path: 导出的文件路径，失败返回 None
        """
        episode = self.db.get(Episode, episode_id)
        if not episode:
            raise ValueError(f"Episode not found: id={episode_id}")

        self.console.print("[cyan]生成营销文案...[/cyan]")
        posts = self.generate_marketing(episode, force_remarketing=force_remarketing)

        if not posts:
            self.console.print("[yellow]无营销文案可导出[/yellow]")
            return None

        self.console.print(f"  共 {len(posts)} 条")
        self.console.print("[cyan]导出到 Obsidian...[/cyan]")

        from app.services.obsidian_service import ObsidianService
        obsidian_service = ObsidianService(self.db)
        try:
            path = obsidian_service.save_marketing_posts(episode_id)
            if path:
                self.console.print(f"  [green]已导出: {path}[/green]")
            return path
        except Exception as e:
            self.console.print(f"  [red]导出失败: {e}[/red]")
            return None

    def distribute_to_platforms(
        self,
        episode: Episode,
        posts: List[MarketingPost]
    ) -> List[PublicationRecord]:
        """
        Publish content to multiple platforms.

        Args:
            episode: Episode to publish
            posts: Marketing posts to publish

        Returns:
            List of PublicationRecord objects
        """
        records = []

        for platform_name, publisher in self.publishers.items():
            self.console.print(f"  发布到 {platform_name}...")

            try:
                # NotionPublisher 使用不同的 API
                if platform_name == "notion":
                    # 只发布 Episode 内容（中英对照翻译、章节分析）
                    # 营销文案不发布到 Notion，用于其他平台
                    episode_record = publisher.publish_episode(episode)
                    records.append(episode_record)

                    status = "成功" if episode_record.status == "success" else "失败"
                    self.console.print(f"    {status}: {episode_record.platform}")

                else:
                    # 其他平台使用 publish 方法
                    # Prepare content for this platform
                    content = {
                        "title": episode.title or f"Episode {episode.id}",
                        "summary": episode.ai_summary or "",
                        "posts": [
                            {
                                "angle_tag": post.angle_tag,
                                "content": post.content
                            }
                            for post in posts
                        ]
                    }

                    # Publish
                    record = publisher.publish(episode, content)
                    records.append(record)

                    status = "成功" if record.status == "success" else "失败"
                    self.console.print(f"    {status}: {record.platform}")

            except Exception as e:
                self.console.print(f"    失败: {str(e)}")

                # Create failure record
                record = PublicationRecord(
                    episode_id=episode.id,
                    platform=platform_name,
                    status="failed",
                    error_message=str(e)
                )
                self.db.add(record)
                records.append(record)

        self.db.commit()
        return records

    def _display_marketing_summary(self, posts: List[MarketingPost]):
        """Display summary of generated marketing posts"""
        table = Table(show_header=True, box=None)
        table.add_column("角度", style="cyan")
        table.add_column("内容预览")

        for post in posts[:5]:  # Show first 5
            preview = post.content[:50] + "..." if len(post.content) > 50 else post.content
            table.add_row(post.angle_tag, preview)

        if len(posts) > 5:
            table.add_row(f"...", f"(共 {len(posts)} 条)")

        panel = Panel(table, title="营销文案", border_style="cyan")
        self.console.print(panel)

    def _display_publication_summary(self, records: List[PublicationRecord]):
        """Display summary of publication results"""
        table = Table(show_header=True, box=None)
        table.add_column("平台", style="cyan")
        table.add_column("状态", style="bold")
        table.add_column("错误信息")

        for record in records:
            status_style = "green" if record.status == "success" else "red"
            status_text = "成功" if record.status == "success" else "失败"
            table.add_row(
                record.platform,
                f"[{status_style}]{status_text}[/{status_style}]",
                record.error_message or ""
            )

        panel = Panel(table, title="发布结果", border_style="blue")
        self.console.print(panel)


__all__ = ["WorkflowPublisher", "Diff"]
