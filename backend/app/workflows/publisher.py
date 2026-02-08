"""
Publish Workflow Orchestrator

Parses Obsidian document edits and publishes to multiple platforms.
"""
from dataclasses import dataclass, field
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

    def publish_workflow(self, episode_id: int, language_code: str = "zh") -> Episode:
        """
        Execute the complete publish workflow.

        Args:
            episode_id: Episode ID
            language_code: 翻译语言代码，默认 "zh"

        Returns:
            Updated Episode with PUBLISHED status

        Raises:
            ValueError: Episode not found or not ready for review
        """
        episode = self.db.get(Episode, episode_id)
        if not episode:
            raise ValueError(f"Episode not found: id={episode_id}")

        # 只允许从 APPROVED 状态发布
        if episode.workflow_status != WorkflowStatus.APPROVED.value:
            current_status = WorkflowStatus(episode.workflow_status)
            raise ValueError(
                f"Episode 状态为 {current_status.label}，"
                f"预期状态为 {WorkflowStatus.APPROVED.label}。"
                f"请先在 Obsidian 中审核并运行 sync_review_status.py"
            )

        # Step 1: Parse Obsidian document for edits
        self.console.print("[cyan]步骤 1/3: 解析 Obsidian 文档...[/cyan]")
        diffs = self.parse_and_backfill(episode, language_code=language_code)

        if diffs:
            self.console.print(f"  检测到 {len(diffs)} 处修改")
        else:
            self.console.print("  无修改")

        # Step 2: Generate marketing content
        self.console.print("[cyan]步骤 2/3: 生成营销文案...[/cyan]")
        posts = self.generate_marketing(episode)

        if posts:
            self.console.print(f"  生成 {len(posts)} 条营销文案")
            self._display_marketing_summary(posts)
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
        Parse Obsidian document and backfill edits to database.

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

    def generate_marketing(self, episode: Episode) -> List[MarketingPost]:
        """
        Generate marketing content for episode.

        Args:
            episode: Episode to process

        Returns:
            List of MarketingPost objects
        """
        if not self.marketing_service:
            self.console.print("  [yellow]警告: 未配置 LLM，跳过营销文案生成[/yellow]")
            return []

        # Generate multi-angle marketing copies
        copies = self.marketing_service.generate_xiaohongshu_copy_multi_angle(episode.id)

        # Save each copy as a MarketingPost
        posts = []
        for i, copy in enumerate(copies):
            angle_tag = copy.metadata.get("angle_name", f"angle_{i+1}")
            post = self.marketing_service.save_marketing_copy(
                episode.id, copy, platform="xhs", angle_tag=angle_tag
            )
            posts.append(post)

        return posts

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
