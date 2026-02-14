#!/usr/bin/env python3
"""
Main Workflow Entry Script

Orchestrates the complete workflow from YouTube URL to Obsidian document.

Usage:
    python scripts/run.py <URL> [--restart] [--force-resegment]

Examples:
    python scripts/run.py https://www.youtube.com/watch?v=dQw4w9WgXcQ
    python scripts/run.py https://www.youtube.com/watch?v=dQw4w9WgXcQ --restart
    python scripts/run.py https://www.youtube.com/watch?v=dQw4w9WgXcQ --force-resegment
"""
import os
import sys
import argparse
from pathlib import Path

# Fix encoding for Windows console
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Parse args before app imports so we can set env for cookies
parser = argparse.ArgumentParser(
    description="运行 EnglishPod3 Enhanced 主工作流",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog="""
示例:
  python scripts/run.py "https://www.youtube.com/watch?v=xxx"
  python scripts/run.py "https://www.youtube.com/watch?v=xxx" --restart
  python scripts/run.py "https://www.youtube.com/watch?v=xxx" --cookies-from-browser chrome
"""
)
parser.add_argument("url", help="YouTube 视频 URL")
parser.add_argument("--restart", action="store_true", help="强制重新开始（忽略断点续传）")
parser.add_argument("--force-resegment", action="store_true",
                    help="强制重新切分（清除旧章节并重新调用 AI）")
parser.add_argument("--cookies-from-browser", metavar="BROWSER",
                    help="使用浏览器 Cookie 绕过 YouTube 机器人检测（如 chrome、firefox）")
parser.add_argument("--cookies", "--cookiefile", dest="cookiefile", metavar="FILE",
                    help="使用 cookies 文件（Netscape 格式，用浏览器扩展导出，更可靠）")

args = parser.parse_args()
if args.cookies_from_browser:
    os.environ["YT_DLP_COOKIES_FROM_BROWSER"] = args.cookies_from_browser
if args.cookiefile:
    os.environ["YT_DLP_COOKIEFILE"] = os.path.abspath(args.cookiefile)

from app.database import get_session
from app.enums.workflow_status import WorkflowStatus
from app.workflows.runner import WorkflowRunner
from rich.console import Console


def main():
    """Main entry point"""

    console = Console()

    # Print header
    console.print()
    console.print("[bold cyan]EnglishPod3 Enhanced - 主工作流[/bold cyan]")
    console.print(f"[dim]URL: {args.url}[/dim]")
    if args.restart:
        console.print("[yellow]模式: 强制重新开始[/yellow]")
    if args.force_resegment:
        console.print("[yellow]模式: 强制重新切分[/yellow]")
    if args.cookies_from_browser:
        console.print(f"[yellow]模式: 使用 {args.cookies_from_browser} Cookie[/yellow]")
    if args.cookiefile:
        console.print(f"[yellow]模式: 使用 cookies 文件 {args.cookiefile}[/yellow]")
    console.print()

    with get_session() as db:
        try:
            runner = WorkflowRunner(db, console)
            episode = runner.run_workflow(
                args.url,
                force_restart=args.restart,
                force_resegment=args.force_resegment,
            )

            console.print()
            console.print(f"[green]成功![/green] Episode ID: {episode.id}")
            status = WorkflowStatus(episode.workflow_status) if isinstance(episode.workflow_status, int) else episode.workflow_status
            console.print(f"[dim]状态: {status.label}[/dim]")
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
