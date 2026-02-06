# Real AI Integration Test: Transcription to Obsidian Flow
"""
Real AI integration test for the complete workflow:
1. Load local audio file
2. Transcribe with Whisper
3. Proofread with LLM
4. Generate Obsidian document
5. Parse Obsidian edits
6. Backfill to database

Usage:
    python scripts/test_transcription_to_obsidian_flow.py
"""
import sys
import os
from pathlib import Path

# Handle Windows console encoding for emoji output
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models import Base, Episode, TranscriptCue, Translation, AudioSegment
from app.enums.workflow_status import WorkflowStatus
from app.utils.file_utils import get_audio_duration
from app.services.transcription_service import TranscriptionService
from app.services.subtitle_proofreading_service import SubtitleProofreadingService
from app.services.obsidian_service import ObsidianService
from app.services.translation_service import TranslationService
from app.services.whisper.whisper_service import WhisperService


def create_test_episode(db: Session, audio_path: Path) -> Episode:
    """
    Create a test episode from local audio file.

    Args:
        db: Database session
        audio_path: Path to audio file

    Returns:
        Episode: Created episode
    """
    import hashlib

    console = Console()

    # Calculate file hash
    file_hash = hashlib.md5(str(audio_path).encode()).hexdigest()

    # Check if episode already exists
    existing = db.query(Episode).filter(Episode.file_hash == file_hash).first()
    if existing:
        console.print(f"[yellow]Episode already exists: {existing.title} (ID: {existing.id})[/yellow]")
        return existing

    # Get audio duration directly
    duration = get_audio_duration(str(audio_path))

    # Create episode
    episode = Episode(
        title=f"Test Episode - {audio_path.stem}",
        file_hash=file_hash,
        source_url=str(audio_path),
        duration=duration,
        workflow_status=WorkflowStatus.INIT
    )
    db.add(episode)
    db.commit()
    db.refresh(episode)

    console.print(f"[green]Created episode: {episode.title} (ID: {episode.id})[/green]")
    console.print(f"  Duration: {duration:.2f} seconds")

    return episode


def transcribe_audio(db: Session, episode: Episode, audio_path: Path) -> list[TranscriptCue]:
    """
    Transcribe audio using Whisper.

    Args:
        db: Database session
        episode: Episode to transcribe
        audio_path: Path to audio file

    Returns:
        List of TranscriptCue objects
    """
    console = Console()

    # Load Whisper models (singleton)
    with console.status("[bold blue]Loading Whisper models..."):
        WhisperService.load_models()

    # Get WhisperService instance
    whisper_service = WhisperService.get_instance()

    with console.status("[bold blue]Transcribing with Whisper..."):
        transcription_service = TranscriptionService(db, whisper_service)
        cues = transcription_service.transcribe_episode(
            episode_id=episode.id,
            audio_path=str(audio_path)
        )

    console.print(f"[green]Transcription complete: {len(cues)} cues[/green]")
    return cues


def proofread_subtitles(db: Session, episode: Episode) -> list[TranscriptCue]:
    """
    Proofread subtitles using LLM.

    Args:
        db: Database session
        episode: Episode to proofread

    Returns:
        List of proofread TranscriptCue objects
    """
    console = Console()

    # Check if LLM is configured
    from app.workflows.publisher import MOONSHOT_API_KEY
    if not MOONSHOT_API_KEY:
        console.print("[yellow]Warning: MOONSHOT_API_KEY not configured, skipping proofreading[/yellow]")
        return db.query(TranscriptCue).filter(
            TranscriptCue.segment_id.in_(
                db.query(AudioSegment.id).filter(AudioSegment.episode_id == episode.id)
            )
        ).all()

    with console.status("[bold blue]Proofreading with LLM..."):
        proofreading_service = SubtitleProofreadingService(db)
        proofreading_service.proofread_episode(episode.id)

    # Get all cues for the episode
    cues = db.query(TranscriptCue).join(AudioSegment).filter(
        AudioSegment.episode_id == episode.id
    ).order_by(TranscriptCue.start_time).all()

    corrected_count = sum(1 for c in cues if c.is_corrected)
    console.print(f"[green]Proofreading complete: {corrected_count}/{len(cues)} cues corrected[/green]")

    return cues


def generate_obsidian_doc(db: Session, episode: Episode, obsidian_path: Path) -> Path:
    """
    Generate Obsidian document.

    Args:
        db: Database session
        episode: Episode to document
        obsidian_path: Path to Obsidian vault

    Returns:
        Path to generated document
    """
    console = Console()

    with console.status("[bold blue]Generating Obsidian document..."):
        obsidian_service = ObsidianService(db, obsidian_path=str(obsidian_path))
        doc_path = obsidian_service.generate_obsidian_doc(episode.id)

    console.print(f"[green]Obsidian document generated: {doc_path}[/green]")
    return doc_path


def translate_subtitles(db: Session, episode: Episode) -> list[Translation]:
    """
    Translate subtitles to Chinese.

    Args:
        db: Database session
        episode: Episode to translate

    Returns:
        List of Translation objects
    """
    console = Console()

    # Check if LLM is configured
    from app.workflows.publisher import MOONSHOT_API_KEY
    if not MOONSHOT_API_KEY:
        console.print("[yellow]Warning: MOONSHOT_API_KEY not configured, skipping translation[/yellow]")
        return []

    with console.status("[bold blue]Translating to Chinese..."):
        translation_service = TranslationService(db)
        translation_service.translate_episode(episode.id, target_language="zh")

    # Get all translations
    translations = db.query(Translation).join(TranscriptCue).join(AudioSegment).filter(
        AudioSegment.episode_id == episode.id
    ).all()

    console.print(f"[green]Translation complete: {len(translations)} translations[/green]")
    return translations


def display_cues_table(console: Console, cues: list[TranscriptCue], title: str = "Transcript Cues"):
    """
    Display cues in a table.

    Args:
        console: Rich console
        cues: List of TranscriptCue objects
        title: Table title
    """
    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("ID", style="dim", width=6)
    table.add_column("Time", style="cyan", width=15)
    table.add_column("Original Text", style="white", no_wrap=False)
    table.add_column("Corrected", style="green", no_wrap=False)
    table.add_column("Is Corrected", justify="center")

    for cue in cues[:20]:  # Show first 20
        corrected_text = cue.corrected_text if cue.corrected_text else "-"
        is_corrected = "✓" if cue.is_corrected else "✗"
        time_str = f"{cue.start_time:.1f}s - {cue.end_time:.1f}s"
        table.add_row(
            str(cue.id),
            time_str,
            cue.text[:50] + "..." if len(cue.text) > 50 else cue.text,
            corrected_text[:50] + "..." if corrected_text and len(corrected_text) > 50 else corrected_text,
            is_corrected
        )

    if len(cues) > 20:
        table.add_row("...", "...", f"... ({len(cues) - 20} more)", "...", "...")

    console.print(table)


def display_translations_table(console: Console, translations: list[Translation], title: str = "Translations"):
    """
    Display translations in a table.

    Args:
        console: Rich console
        translations: List of Translation objects
        title: Table title
    """
    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("ID", style="dim", width=6)
    table.add_column("Cue ID", style="cyan", width=8)
    table.add_column("Original", style="white", no_wrap=False)
    table.add_column("Translation", style="green", no_wrap=False)
    table.add_column("Is Edited", justify="center")

    for t in translations[:20]:  # Show first 20
        is_edited = "✓" if t.is_edited else "✗"
        table.add_row(
            str(t.id),
            str(t.cue_id),
            t.original_translation[:40] + "..." if t.original_translation and len(t.original_translation) > 40 else (t.original_translation or "-"),
            t.translation[:40] + "..." if t.translation and len(t.translation) > 40 else (t.translation or "-"),
            is_edited
        )

    if len(translations) > 20:
        table.add_row("...", "...", "...", f"... ({len(translations) - 20} more)", "...")

    console.print(table)


def parse_obsidian_edits(db: Session, episode: Episode, obsidian_path: Path) -> dict:
    """
    Parse Obsidian document for edits.

    Args:
        db: Database session
        episode: Episode to parse
        obsidian_path: Path to Obsidian vault

    Returns:
        Parsed data dictionary
    """
    console = Console()

    obsidian_service = ObsidianService(db, obsidian_path=str(obsidian_path))

    doc_path = obsidian_service._get_episode_path(episode.id)
    if not doc_path or not doc_path.exists():
        console.print(f"[yellow]Obsidian document not found: {doc_path}[/yellow]")
        return {}

    with console.status("[bold blue]Parsing Obsidian document..."):
        parsed_data = obsidian_service.parse_episode(episode.id)

    if parsed_data.get("translations"):
        console.print(f"[green]Found {len(parsed_data['translations'])} translation edits in Obsidian[/green]")
    else:
        console.print("[yellow]No translation edits found in Obsidian document[/yellow]")

    return parsed_data


def backfill_edits(db: Session, episode: Episode, parsed_data: dict) -> list:
    """
    Backfill Obsidian edits to database.

    Args:
        db: Database session
        episode: Episode to backfill
        parsed_data: Parsed data from Obsidian

    Returns:
        List of Diff objects
    """
    console = Console()

    from app.workflows.publisher import WorkflowPublisher, Diff

    publisher = WorkflowPublisher(db, Console())

    with console.status("[bold blue]Backfilling edits to database..."):
        diffs = publisher.parse_and_backfill(episode)

    if diffs:
        console.print(f"[green]Backfilled {len(diffs)} edits to database[/green]")
        for diff in diffs[:5]:
            console.print(f"  - Cue {diff.cue_id}: {diff.field} changed")
        if len(diffs) > 5:
            console.print(f"  ... and {len(diffs) - 5} more")
    else:
        console.print("[yellow]No changes to backfill[/yellow]")

    return diffs


def main():
    """Main test function."""
    console = Console()

    console.print(Panel.fit("[bold cyan]Real AI Integration Test: Transcription to Obsidian Flow[/bold cyan]"))

    # Configuration
    audio_path = Path(r"D:\programming_enviroment\learning-EnglishPod3\backend\data\sample_audio\003.mp3")
    obsidian_path = Path(r"D:\programming_enviroment\EnglishPod-knowledgeBase\backend\data\obsidian_vault")

    # Validate paths
    if not audio_path.exists():
        console.print(f"[red]Error: Audio file not found: {audio_path}[/red]")
        return

    obsidian_path.mkdir(parents=True, exist_ok=True)

    # Use in-memory database for isolation
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        try:
            # Step 1: Create episode
            console.print("\n[bold yellow]Step 1: Creating Episode[/bold yellow]")
            episode = create_test_episode(db, audio_path)

            # Step 2: Transcribe
            console.print("\n[bold yellow]Step 2: Transcribing Audio[/bold yellow]")
            cues = transcribe_audio(db, episode, audio_path)
            display_cues_table(console, cues, "Transcription Results")

            # Step 3: Proofread
            console.print("\n[bold yellow]Step 3: Proofreading with LLM[/bold yellow]")
            cues = proofread_subtitles(db, episode)
            display_cues_table(console, cues, "Proofreading Results")

            # Step 4: Translate
            console.print("\n[bold yellow]Step 4: Translating to Chinese[/bold yellow]")
            translations = translate_subtitles(db, episode)
            if translations:
                display_translations_table(console, translations, "Translation Results")

            # Step 5: Generate Obsidian document
            console.print("\n[bold yellow]Step 5: Generating Obsidian Document[/bold yellow]")
            doc_path = generate_obsidian_doc(db, episode, obsidian_path)
            console.print(f"[dim]Document saved to: {doc_path}[/dim]")

            # Step 6: Parse Obsidian for edits (simulate manual edit)
            console.print("\n[bold yellow]Step 6: Parsing Obsidian Document[/bold yellow]")
            console.print("[dim]Note: For testing, you can manually edit the Obsidian document and run this step again[/dim]")
            parsed_data = parse_obsidian_edits(db, episode, obsidian_path)

            # Step 7: Backfill edits
            console.print("\n[bold yellow]Step 7: Backfilling Edits to Database[/bold yellow]")
            diffs = backfill_edits(db, episode, parsed_data)

            # Summary
            console.print("\n[bold green]Test Complete![/bold green]")
            console.print(Panel.fit(
                f"""Episode ID: {episode.id}
Title: {episode.title}
Cues: {len(cues)}
Translations: {len(translations)}
Edits Backfilled: {len(diffs)}
Obsidian Doc: {doc_path}"""
            ))

            console.print("\n[dim]Tip: You can now manually edit the Obsidian document at:[/dim]")
            console.print(f"[dim]{doc_path}[/dim]")
            console.print("[dim]Then run this script again to test the backfill functionality.[/dim]")

        except Exception as e:
            console.print(f"\n[red]Error: {e}[/red]")
            import traceback
            console.print(traceback.format_exc())


if __name__ == "__main__":
    main()
