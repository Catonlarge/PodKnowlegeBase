"""
审核状态同步脚本

功能：
1. 扫描 Obsidian 目录中的所有 Markdown 文件
2. 检测 YAML Frontmatter 中的 status 字段
3. 将 status=approved 的 Episode 同步到数据库
4. 更新 Episode.workflow_status = PUBLISHED

使用方法：
    python scripts/sync_review_status.py
"""
import sys
from pathlib import Path

# Fix encoding for Windows console
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from app.models import Base
from app.config import DATABASE_PATH
from app.services.review_service import ReviewService
from app.enums.workflow_status import WorkflowStatus


def main():
    """主函数"""
    console = Console()

    console.print(Panel.fit(
        "[bold blue]审核状态同步脚本[/bold blue]",
        subtitle="Obsidian → Database"
    ))

    # 创建数据库会话
    engine = create_engine(
        f"sqlite:///{DATABASE_PATH}",
        connect_args={"check_same_thread": False}
    )

    SessionFactory = sessionmaker(bind=engine)
    db = SessionFactory()

    try:
        # 创建服务实例
        review_service = ReviewService(db)

        # 打印审核摘要
        review_service.print_review_summary()

        # 获取待审核的 Episode
        pending = review_service.get_pending_review_episodes()
        if pending:
            console.print(f"\n[yellow]数据库中有 {len(pending)} 个 Episode 状态为 READY_FOR_REVIEW[/yellow]")
            for ep in pending[:5]:
                console.print(f"  - ID {ep.id}: {ep.title[:50]}...")
            if len(pending) > 5:
                console.print(f"  ... 还有 {len(pending) - 5} 个")

        # 扫描 Obsidian 文件状态
        console.print("\n[cyan]扫描 Obsidian 文档...[/cyan]")
        statuses = review_service.scan_review_status()

        if not statuses:
            console.print("[yellow]未找到任何 Obsidian 文档[/yellow]")
            return

        # 显示扫描结果
        table = Table(title="Obsidian 文档审核状态")
        table.add_column("Episode ID", style="cyan")
        table.add_column("Status", style="yellow")
        table.add_column("File", style="white")

        for s in statuses:
            status_style = "[green]approved[/green]" if s.status == "approved" else f"[yellow]{s.status}[/yellow]"
            table.add_column(str(s.episode_id))
            table.add_column(status_style)
            table.add_column(str(s.file_path.name))

        console.print(table)

        # 统计
        approved_count = sum(1 for s in statuses if s.status == "approved")
        pending_count = sum(1 for s in statuses if s.status == "pending_review")

        console.print(f"\n[bold]统计:[/bold]")
        console.print(f"  待审核 (pending_review): {pending_count}")
        console.print(f"  已通过 (approved): {approved_count}")

        if approved_count == 0:
            console.print("\n[yellow]没有已审核通过的文档，同步结束[/yellow]")
            return

        # 确认同步
        console.print(f"\n[yellow]将同步 {approved_count} 个已审核通过的 Episode 到数据库[/yellow]")
        confirm = input("确认继续? (y/n): ").strip().lower()

        if confirm != 'y':
            console.print("[yellow]已取消[/yellow]")
            return

        # 执行同步
        console.print("\n[cyan]同步到数据库...[/cyan]")
        count = review_service.sync_approved_episodes()

        console.print(f"\n[green]成功同步 {count} 个 Episode[/green]")

        # 显示已发布的 Episode
        console.print("\n[bold]已发布的 Episode:[/bold]")
        published_episodes = db.query(Episode).filter(
            Episode.workflow_status == WorkflowStatus.PUBLISHED.value
        ).all()

        if published_episodes:
            pub_table = Table()
            pub_table.add_column("ID", style="cyan")
            pub_table.add_column("Title", style="white")
            pub_table.add_column("Status", style="green")

            for ep in published_episodes[:10]:
                pub_table.add_row(str(ep.id), ep.title[:40], "PUBLISHED")

            console.print(pub_table)

            if len(published_episodes) > 10:
                console.print(f"... 还有 {len(published_episodes) - 10} 个")

    except Exception as e:
        console.print(f"\n[red]错误: {e}[/red]")
        import traceback
        traceback.print_exc()

    finally:
        db.close()
        console.print("\n[dim]脚本执行完成[/dim]")


if __name__ == "__main__":
    main()
