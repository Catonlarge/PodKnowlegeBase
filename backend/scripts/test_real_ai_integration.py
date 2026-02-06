"""
Real AI Integration End-to-End Test

This script tests the complete workflow with REAL AI API calls.
Supports both YouTube URLs and local audio files.

Usage:
    # With YouTube URL
    $env:MOONSHOT_API_KEY="your_api_key"
    python scripts/test_real_ai_integration.py --url "https://www.youtube.com/watch?v=xxx"

    # With local audio file
    python scripts/test_real_ai_integration.py --file "path/to/audio.mp3"

    # Interactive mode (will prompt for input)
    python scripts/test_real_ai_integration.py

Workflow:
1. Download/Load Audio
2. Transcribe (WhisperX)
3. Proofread Subtitles (Moonshot API)
4. Semantic Segmentation (Moonshot API)
5. Translate (Moonshot API)
6. Generate Marketing Content (Moonshot API)
7. Generate Obsidian Document
"""
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime

# Fix encoding for Windows console
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.services.download_service import DownloadService
from app.services.whisper.whisper_service import WhisperService
from app.services.transcription_service import TranscriptionService
from app.services.subtitle_proofreading_service import SubtitleProofreadingService
from app.services.segmentation_service import SegmentationService
from app.services.translation_service import TranslationService
from app.services.marketing_service import MarketingService
from app.services.obsidian_service import ObsidianService
from app.services.ai.ai_service import AIService
from app.models import (
    Base, Episode, AudioSegment, TranscriptCue, Translation,
    Chapter, MarketingPost
)
from app.enums.workflow_status import WorkflowStatus
from app.utils.file_utils import calculate_md5_sync, get_audio_duration
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn


def create_test_session(db_path: str = None) -> Session:
    """Create a SQLite database session for testing."""
    if db_path:
        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
    else:
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
    Base.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine)
    return SessionFactory()


def is_youtube_url(url: str) -> bool:
    """Check if URL is a YouTube URL."""
    return bool(any(domain in url.lower() for domain in [
        "youtube.com", "youtu.be", "www.youtube.com", "m.youtube.com"
    ]))


def get_url_title(url: str) -> str:
    """Try to get title from URL."""
    try:
        if is_youtube_url(url):
            # For YouTube, we'll return a generic title
            # Actual download will get the real title
            return f"YouTube Video ({url[:30]}...)"
        return f"Audio from {url[:50]}"
    except:
        return "Unknown Audio"


def test_workflow_with_url(
    db: Session,
    url: str,
    console: Console,
    skip_download: bool = False,
    audio_file: str = None
) -> bool:
    """
    Run the complete workflow with a real URL or audio file.

    Args:
        db: Database session
        url: Source URL (or None if using local file)
        console: Rich console instance
        skip_download: Skip download step, use existing file
        audio_file: Path to local audio file

    Returns:
        bool: True if all tests passed
    """
    results = {}

    # ========================================================================
    # Step 1: Download / Load Audio
    # ========================================================================
    console.print(Panel.fit("[bold cyan]Step 1: Audio Source[/bold cyan]"))

    try:
        local_audio_path = None

        if audio_file and Path(audio_file).exists():
            # Use local audio file
            local_audio_path = Path(audio_file)
            console.print(f"[green]Using local audio file: {local_audio_path}[/green]")
            url = str(local_audio_path)  # Use file path as URL
        elif skip_download and audio_file:
            local_audio_path = Path(audio_file)
            console.print(f"[yellow]Skipping download, using: {local_audio_path}[/yellow]")
        elif url and is_youtube_url(url):
            console.print(f"[cyan]YouTube URL detected: {url}[/cyan]")
            console.print("[yellow]Download would start here...[/yellow]")
            console.print("[yellow]Note: For quick testing, use --file with a local audio file[/yellow]")
            return False
        elif url and Path(url).exists():
            # URL is actually a local file path
            local_audio_path = Path(url)
            console.print(f"[green]Using audio file from URL param: {local_audio_path}[/green]")
        else:
            console.print(f"[red]Invalid URL or file not found: {url}[/red]")
            return False

        # Get audio info
        file_hash = calculate_md5_sync(str(local_audio_path))
        duration = get_audio_duration(str(local_audio_path))

        console.print(f"  File: {local_audio_path.name}")
        console.print(f"  Size: {local_audio_path.stat().st_size / 1024 / 1024:.2f} MB")
        console.print(f"  Duration: {duration:.1f} seconds ({duration/60:.1f} minutes)")
        console.print(f"  Hash: {file_hash[:16]}...")

        # Check for existing episode
        existing = db.query(Episode).filter(Episode.file_hash == file_hash).first()
        if existing:
            console.print(f"[yellow]Episode already exists: {existing.title} (ID: {existing.id})[/yellow]")
            episode = existing
        else:
            episode = Episode(
                title=get_url_title(url) if url else local_audio_path.stem,
                file_hash=file_hash,
                source_url=url or str(local_audio_path),
                duration=duration,
                workflow_status=WorkflowStatus.DOWNLOADED
            )
            db.add(episode)
            db.flush()
            console.print(f"[green]Created new episode: {episode.title} (ID: {episode.id})[/green]")

        results["audio_source"] = True

    except Exception as e:
        console.print(f"[red]Step 1 FAILED: {e}[/red]")
        import traceback
        traceback.print_exc()
        return False

    # ========================================================================
    # Step 2: Transcribe (WhisperX)
    # ========================================================================
    console.print(Panel.fit("[bold cyan]Step 2: Transcription (WhisperX)[/bold cyan]"))

    try:
        # Update episode with audio path (required for transcription)
        episode.audio_path = str(local_audio_path)
        db.commit()

        console.print("[cyan]Loading WhisperX model...[/cyan]")
        WhisperService.load_models()
        whisper_service = WhisperService.get_instance()

        transcription_service = TranscriptionService(db, whisper_service)

        console.print(f"[cyan]Transcribing: {local_audio_path}[/cyan]")
        transcription_service.segment_and_transcribe(
            episode_id=episode.id,
            enable_diarization=True
        )

        # Get the created cues
        cues = db.query(TranscriptCue).join(
            AudioSegment, TranscriptCue.segment_id == AudioSegment.id
        ).filter(
            AudioSegment.episode_id == episode.id
        ).order_by(TranscriptCue.start_time).all()

        console.print(f"[green]Transcription complete: {len(cues)} cues[/green]")

        # Show preview
        console.print("\n[bold]Transcript preview (first 3):[/bold]")
        for cue in cues[:3]:
            console.print(f"  [{cue.start_time:.1f}s] {cue.speaker}: {cue.text}")

        # Update episode status
        episode.workflow_status = WorkflowStatus.TRANSCRIBED
        db.commit()

        results["transcription"] = True

    except Exception as e:
        console.print(f"[red]Step 2 FAILED: {e}[/red]")
        import traceback
        traceback.print_exc()
        results["transcription"] = False

    # ========================================================================
    # Step 3: Proofread Subtitles (Moonshot API)
    # ========================================================================
    console.print(Panel.fit("[bold cyan]Step 3: Subtitle Proofreading (Moonshot API)[/bold cyan]"))

    try:
        proofreading_service = SubtitleProofreadingService(db)

        console.print("[cyan]Scanning for subtitle corrections...[/cyan]")
        proofread_result = proofreading_service.scan_and_correct(
            episode_id=episode.id,
            batch_size=20,
            apply=True
        )

        table = Table(title="Proofreading Results")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Total Cues", str(proofread_result.total_cues))
        table.add_row("Corrections", str(proofread_result.corrected_count))
        table.add_row("Skipped", str(proofread_result.skipped_count))
        console.print(table)

        if proofread_result.corrections:
            console.print("\n[yellow]Sample corrections:[/yellow]")
            for corr in proofread_result.corrections[:2]:
                console.print(f"  Cue {corr.cue_id}: {corr.original_text[:40]}...")
                console.print(f"  -> {corr.corrected_text[:40]}...")
                console.print(f"  Reason: {corr.reason}")

        episode.workflow_status = WorkflowStatus.PROOFREAD
        db.commit()
        results["proofreading"] = True

    except Exception as e:
        console.print(f"[red]Step 3 FAILED: {e}[/red]")
        import traceback
        traceback.print_exc()
        results["proofreading"] = False

    # ========================================================================
    # Step 4: Semantic Segmentation (Moonshot API)
    # ========================================================================
    console.print(Panel.fit("[bold cyan]Step 4: Semantic Segmentation (Moonshot API)[/bold cyan]"))

    try:
        ai_service = AIService(provider="moonshot")
        segmentation_service = SegmentationService(db, ai_service)

        console.print("[cyan]Analyzing and segmenting content...[/cyan]")
        chapters = segmentation_service.analyze_and_segment(episode.id)

        table = Table(title="Chapters")
        table.add_column("#", style="cyan")
        table.add_column("Time Range", style="yellow")
        table.add_column("Title", style="green")
        for i, ch in enumerate(chapters, 1):
            time_range = f"{ch.start_time:.0f}s - {ch.end_time:.0f}s"
            table.add_row(str(i), time_range, ch.title[:40])
        console.print(table)
        console.print(f"[green]Generated {len(chapters)} chapters[/green]")

        episode.workflow_status = WorkflowStatus.SEGMENTED
        db.commit()
        results["segmentation"] = True

    except Exception as e:
        console.print(f"[red]Step 4 FAILED: {e}[/red]")
        import traceback
        traceback.print_exc()
        results["segmentation"] = False

    # ========================================================================
    # Step 5: Translation (Moonshot API)
    # ========================================================================
    console.print(Panel.fit("[bold cyan]Step 5: Translation (Moonshot API)[/bold cyan]"))

    try:
        ai_service = AIService(provider="moonshot")
        translation_service = TranslationService(db, ai_service)

        console.print("[cyan]Translating to Chinese...[/cyan]")
        count = translation_service.batch_translate(
            episode_id=episode.id,
            language_code="zh"
        )

        console.print(f"[green]Translated {count} cues[/green]")

        # Show sample
        translations = db.query(Translation).join(TranscriptCue).join(
            AudioSegment
        ).filter(
            AudioSegment.episode_id == episode.id,
            Translation.language_code == "zh"
        ).limit(3).all()

        for t in translations:
            console.print(f"  [{t.cue.text[:30]}...]")
            console.print(f"  -> {t.translation[:40]}...")

        episode.workflow_status = WorkflowStatus.TRANSLATED
        db.commit()
        results["translation"] = True

    except Exception as e:
        console.print(f"[red]Step 5 FAILED: {e}[/red]")
        import traceback
        traceback.print_exc()
        results["translation"] = False

    # ========================================================================
    # Step 6: Marketing Content (Moonshot API)
    # ========================================================================
    console.print(Panel.fit("[bold cyan]Step 6: Marketing Content (Moonshot API)[/bold cyan]"))

    try:
        marketing_service = MarketingService(db)

        console.print("[cyan]Generating marketing posts...[/cyan]")

        # Generate different angle tags
        angles = ["干货硬核向", "职场焦虑向", "情感共鸣向"]
        posts = []

        for angle in angles:
            copy = marketing_service.generate_xiaohongshu_copy(episode.id)
            post = marketing_service.save_marketing_copy(
                episode_id=episode.id,
                copy=copy,
                platform="xhs",
                angle_tag=angle
            )
            posts.append(post)

        table = Table(title="Marketing Posts")
        table.add_column("Angle", style="cyan")
        table.add_column("Title", style="yellow")
        table.add_column("Content Preview", style="white")
        for p in posts:
            preview = p.content[:60] + "..." if len(p.content) > 60 else p.content
            table.add_row(p.angle_tag, p.title[:30], preview)
        console.print(table)
        console.print(f"[green]Generated {len(posts)} posts[/green]")

        results["marketing"] = True

    except Exception as e:
        console.print(f"[red]Step 6 FAILED: {e}[/red]")
        import traceback
        traceback.print_exc()
        results["marketing"] = False

    # ========================================================================
    # Step 7: Obsidian Document (Episode)
    # ========================================================================
    console.print(Panel.fit("[bold cyan]Step 7: Obsidian Document Generation (Episode)[/bold cyan]"))

    try:
        obsidian_service = ObsidianService(db, vault_path=None)
        file_path = obsidian_service.save_episode(episode.id, language_code="zh")

        console.print(f"[green]Episode document created: {file_path}[/green]")
        console.print(f"  File size: {file_path.stat().st_size / 1024:.1f} KB")

        episode.workflow_status = WorkflowStatus.READY_FOR_REVIEW
        db.commit()
        results["obsidian"] = True

    except Exception as e:
        console.print(f"[red]Step 7 FAILED: {e}[/red]")
        import traceback
        traceback.print_exc()
        results["obsidian"] = False

    # ========================================================================
    # Step 8: Obsidian Document (Marketing)
    # ========================================================================
    console.print(Panel.fit("[bold cyan]Step 8: Obsidian Document Generation (Marketing)[/bold cyan]"))

    try:
        obsidian_service = ObsidianService(db, vault_path=None)
        marketing_file_path = obsidian_service.save_marketing_posts(episode.id)

        if marketing_file_path:
            console.print(f"[green]Marketing document created: {marketing_file_path}[/green]")
            console.print(f"  File size: {marketing_file_path.stat().st_size / 1024:.1f} KB")
        else:
            console.print("[yellow]No marketing posts to save[/yellow]")

        results["marketing_obsidian"] = True

    except Exception as e:
        console.print(f"[red]Step 8 FAILED: {e}[/red]")
        import traceback
        traceback.print_exc()
        results["marketing_obsidian"] = False

    return all(results.values())


def print_summary(console: Console, results: dict, episode_id: int):
    """Print test summary."""
    console.print(Panel.fit("[bold magenta]Workflow Test Summary[/bold magenta]"))

    table = Table()
    table.add_column("Step", style="cyan")
    table.add_column("Status", style="bold")

    step_names = {
        "audio_source": "1. Audio Source",
        "transcription": "2. Transcription",
        "proofreading": "3. Proofreading",
        "segmentation": "4. Segmentation",
        "translation": "5. Translation",
        "marketing": "6. Marketing Content",
        "obsidian": "7. Obsidian (Episode)",
        "marketing_obsidian": "8. Obsidian (Marketing)"
    }

    for key, passed in results.items():
        name = step_names.get(key, key)
        status = "[green]PASSED[/green]" if passed else "[red]FAILED[/red]"
        table.add_row(name, status)

    console.print(table)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    console.print(f"\n[bold]Episode ID: {episode_id}[/bold]")
    console.print(f"[bold]Results: {passed}/{total} steps passed[/bold]")

    if passed == total:
        console.print("\n[green bold]All steps PASSED! Real AI integration verified.[/green bold]")
    else:
        console.print(f"\n[yellow]{total - passed} step(s) failed. Check errors above.[/yellow]")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Real AI Integration End-to-End Test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # With YouTube URL
  python scripts/test_real_ai_integration.py --url "https://www.youtube.com/watch?v=xxx"

  # With local audio file
  python scripts/test_real_ai_integration.py --file "path/to/audio.mp3"

  # Interactive mode
  python scripts/test_real_ai_integration.py
        """
    )

    parser.add_argument("--url", help="YouTube URL or audio source URL")
    parser.add_argument("--file", help="Path to local audio file")
    parser.add_argument("--db", help="Path to database file (default: in-memory)")

    args = parser.parse_args()

    console = Console()

    console.print(Panel.fit(
        "[bold blue]Real AI Integration End-to-End Test[/bold blue]",
        subtitle="Testing: Whisper | Moonshot API | Obsidian"
    ))

    # Check API Key
    if not os.environ.get("MOONSHOT_API_KEY"):
        console.print("[red]ERROR: MOONSHOT_API_KEY not set![/red]")
        console.print("\nSet it with:")
        console.print("  PowerShell: $env:MOONSHOT_API_KEY='your_api_key'")
        console.print("  CMD: set MOONSHOT_API_KEY=your_api_key")
        return

    console.print("[green]API Key detected[/green]\n")

    # Determine input source
    url = args.url
    audio_file = args.file

    if not url and not audio_file:
        # Interactive mode
        console.print("[yellow]No URL or file specified. Enter input source:[/yellow]")
        console.print("  1. YouTube URL")
        console.print("  2. Local audio file")

        choice = input("\nEnter choice (1 or 2): ").strip()

        if choice == "1":
            url = input("Enter YouTube URL: ").strip()
        elif choice == "2":
            audio_file = input("Enter path to audio file: ").strip()
        else:
            console.print("[red]Invalid choice[/red]")
            return

    # Validate input
    if url and is_youtube_url(url):
        console.print(f"\n[cyan]YouTube URL: {url}[/cyan]")
        console.print("[yellow]Note: YouTube download requires yt-dlp setup[/yellow]")
        console.print("[yellow]For quick testing, use --file with a local audio file[/yellow]")
        confirm = input("\nContinue with YouTube? (y/n): ").strip().lower()
        if confirm != 'y':
            return
    elif audio_file:
        if not Path(audio_file).exists():
            console.print(f"[red]File not found: {audio_file}[/red]")
            return
        console.print(f"\n[cyan]Audio file: {audio_file}[/cyan]")
    else:
        console.print("[red]Please provide a valid YouTube URL or audio file path[/red]")
        return

    # Setup database
    db_path = args.db or "./data/test_real_ai_integration.db"
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    console.print(f"\n[bold]Database: {db_path}[/bold]")
    db = create_test_session(db_path)

    try:
        # Run workflow
        success = test_workflow_with_url(
            db=db,
            url=url,
            audio_file=audio_file,
            console=console
        )

        if success:
            console.print("\n[green bold]Workflow completed successfully![/green bold]")
        else:
            console.print("\n[red bold]Workflow had errors. Check output above.[/red bold]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Test interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"\n[red]FATAL ERROR: {e}[/red]")
        import traceback
        traceback.print_exc()
    finally:
        db.close()
        console.print("\n[bold]Test session closed[/bold]")


if __name__ == "__main__":
    main()
