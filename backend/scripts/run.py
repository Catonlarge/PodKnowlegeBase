#!/usr/bin/env python3
"""
Main Workflow Entry Script

Orchestrates the complete workflow from YouTube URL to Obsidian document.

Usage:
    python scripts/run.py <URL> [--restart]

Examples:
    python scripts/run.py https://www.youtube.com/watch?v=dQw4w9WgXcQ
    python scripts/run.py https://www.youtube.com/watch?v=dQw4w9WgXcQ --restart
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
from app.workflows.runner import WorkflowRunner
from rich.console import Console


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="运行 EnglishPod3 Enhanced 主工作流",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/run.py https://www.youtube.com/watch?v=xxx
  python scripts/run.py https://www.youtube.com/watch?v=xxx --restart
        """
    )
    parser.add_argument("url", help="YouTube 视频 URL")
    parser.add_argument("--restart", action="store_true", help="强制重新开始（忽略断点续传）")

    args = parser.parse_args()

    console = Console()

    # Print header
    console.print()
    console.print("[bold cyan]EnglishPod3 Enhanced - 主工作流[/bold cyan]")
    console.print(f"[dim]URL: {args.url}[/dim]")
    if args.restart:
        console.print("[yellow]模式: 强制重新开始[/yellow]")
    console.print()

    db = get_session()

    try:
        runner = WorkflowRunner(db, console)
        episode = runner.run_workflow(args.url, force_restart=args.restart)

        console.print()
        console.print(f"[green]成功![/green] Episode ID: {episode.id}")
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

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
