#!/usr/bin/env python3
"""
Publish Workflow Entry Script

Parses Obsidian document edits and publishes to multiple platforms.

Usage:
    python scripts/publish.py --id <EPISODE_ID>

Examples:
    python scripts/publish.py --id 42
"""
import sys
import argparse
from pathlib import Path

# Fix encoding for Windows console
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import get_session
from app.workflows.publisher import WorkflowPublisher
from rich.console import Console


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="运行 EnglishPod3 Enhanced 发布工作流",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/publish.py --id 42
        """
    )
    parser.add_argument("--id", type=int, required=True, help="Episode ID")

    args = parser.parse_args()

    console = Console()

    # Print header
    console.print()
    console.print("[bold cyan]EnglishPod3 Enhanced - 发布工作流[/bold cyan]")
    console.print(f"[dim]Episode ID: {args.id}[/dim]")
    console.print()

    with get_session() as db:
        try:
            publisher = WorkflowPublisher(db, console)
            episode = publisher.publish_workflow(args.id)

            console.print()
            console.print(f"[green]发布成功![/green] Episode ID: {episode.id}")
            console.print(f"[dim]状态: {episode.workflow_status.label}[/dim]")
            console.print()

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
