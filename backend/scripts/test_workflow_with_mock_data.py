# Workflow Integration Test with Mock Data
"""
Integration test for the complete workflow using mock transcription data.
Tests the Obsidian generation, parsing, and backfilling flow without requiring
Whisper model downloads.

Usage:
    python scripts/test_workflow_with_mock_data.py
"""
import sys
from pathlib import Path

# Handle Windows console encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models import Base, Episode, TranscriptCue, Translation, AudioSegment
from app.enums.workflow_status import WorkflowStatus
from app.services.obsidian_service import ObsidianService
from app.workflows.publisher import WorkflowPublisher, Diff


def create_mock_episode_with_data(db: Session) -> Episode:
    """
    Create a mock episode with sample transcription and translation data.

    Args:
        db: Database session

    Returns:
        Episode: Created episode with data
    """
    console = Console()

    # Create episode
    episode = Episode(
        title="Sample Episode: Daily English Conversation",
        file_hash="mock_test_001",
        source_url="https://example.com/sample.mp3",
        duration=180.0,
        workflow_status=WorkflowStatus.TRANSCRIBED,
        ai_summary="A casual conversation about daily activities."
    )
    db.add(episode)
    db.flush()

    # Create audio segment
    segment = AudioSegment(
        episode_id=episode.id,
        segment_index=0,
        segment_id="segment_001",
        start_time=0.0,
        end_time=180.0
    )
    db.add(segment)
    db.flush()

    # Sample transcription data (simulating Whisper output)
    sample_cues = [
        (0.0, 3.5, "Hello, how are you doing today?", "SPEAKER_00"),
        (3.5, 7.2, "I'm doing great, thanks for asking! What about you?", "SPEAKER_01"),
        (7.2, 12.0, "Pretty good! I've been busy with work lately.", "SPEAKER_00"),
        (12.0, 16.5, "Yeah, same here. By the way, did you finish that report?", "SPEAKER_01"),
        (16.5, 21.0, "Not yet, I'm planning to work on it this weekend.", "SPEAKER_00"),
        (21.0, 25.3, "That sounds good. Let me know if you need any help.", "SPEAKER_01"),
        (25.3, 30.0, "Sure thing! I appreciate it.", "SPEAKER_00"),
        (30.0, 35.0, "Oh, before I forget, are you coming to the meeting tomorrow?", "SPEAKER_01"),
        (35.0, 40.0, "Yes, I'll be there at 2 PM as scheduled.", "SPEAKER_00"),
        (40.0, 45.0, "Perfect! See you then.", "SPEAKER_01"),
    ]

    # Create transcript cues
    for start, end, text, speaker in sample_cues:
        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=start,
            end_time=end,
            text=text,
            speaker=speaker
        )
        db.add(cue)

    db.flush()

    # Create translations (Chinese)
    translations_data = [
        "你好，今天怎么样？",
        "我很好，谢谢关心！你呢？",
        "还不错！最近工作挺忙的。",
        "是啊，我也是。顺便问一下，你完成那份报告了吗？",
        "还没呢，我打算这周末处理。",
        "听起来不错。如果需要帮忙尽管说。",
        "好的！非常感谢。",
        "哦，差点忘了，你明天来开会吗？",
        "来，我会按计划在下午两点到。",
        "太好了！到时候见。",
    ]

    cues = db.query(TranscriptCue).filter(TranscriptCue.segment_id == segment.id).all()
    for cue, translation_text in zip(cues, translations_data):
        translation = Translation(
            cue_id=cue.id,
            language_code="zh",
            translation=translation_text,
            original_translation=translation_text,
            is_edited=False,
            translation_status="completed"
        )
        db.add(translation)

    db.commit()
    db.refresh(episode)

    console.print(f"[green]Created mock episode with {len(cues)} cues and translations[/green]")
    return episode


def display_episode_data(console: Console, episode: Episode):
    """Display episode data in tables."""
    # Get cues and translations
    cues = db.query(TranscriptCue).join(AudioSegment).filter(
        AudioSegment.episode_id == episode.id
    ).order_by(TranscriptCue.start_time).all()

    # Display cues
    cues_table = Table(title=f"Transcript Cues (Episode: {episode.title})", show_header=True)
    cues_table.add_column("Time", style="cyan")
    cues_table.add_column("Speaker", style="yellow")
    cues_table.add_column("English", style="white")
    cues_table.add_column("Chinese", style="green")

    for cue in cues:
        translation = cue.translations[0] if cue.translations else None
        time_str = f"{cue.start_time:.1f}s - {cue.end_time:.1f}s"
        cues_table.add_row(
            time_str,
            cue.speaker,
            cue.text,
            translation.translation if translation else "-"
        )

    console.print(cues_table)


def generate_obsidian_document(db: Session, episode: Episode, obsidian_path: Path) -> Path:
    """Generate Obsidian document from episode data."""
    console = Console()

    console.print("\n[bold yellow]Step 1: Generating Obsidian Document[/bold yellow]")

    obsidian_service = ObsidianService(db, obsidian_path=str(obsidian_path))
    doc_path = obsidian_service.generate_obsidian_doc(episode.id)

    console.print(f"[green]Document generated: {doc_path}[/green]")

    # Display document content
    if doc_path.exists():
        content = doc_path.read_text(encoding='utf-8')
        console.print("\n[bold]Generated Document Preview:[/bold]")
        # Show first 50 lines
        lines = content.split('\n')[:50]
        preview = '\n'.join(lines)
        if len(content.split('\n')) > 50:
            preview += "\n... (truncated)"

        syntax = Syntax(preview, "markdown", theme="monokai", line_numbers=True)
        console.print(syntax)

    return doc_path


def parse_obsidian_document(db: Session, episode: Episode, obsidian_path: Path) -> dict:
    """Parse Obsidian document for changes."""
    console = Console()

    console.print("\n[bold yellow]Step 2: Parsing Obsidian Document[/bold yellow]")

    obsidian_service = ObsidianService(db, obsidian_path=str(obsidian_path))
    parsed_data = obsidian_service.parse_episode(episode.id)

    console.print(f"[green]Parsed {len(parsed_data.get('translations', {}))} translation entries[/green]")

    return parsed_data


def simulate_manual_edit(doc_path: Path) -> dict:
    """
    Simulate manual editing of Obsidian document.
    In real usage, user would edit the file in Obsidian.

    Returns dict of mock edits (cue_id -> new_translation)
    """
    console = Console()

    console.print("\n[bold yellow]Simulating Manual Edits...[/bold yellow]")

    # Read current content
    content = doc_path.read_text(encoding='utf-8')

    # Mock edits: change some translations
    mock_edits = {
        # Change "你好，今天怎么样？" to "嘿，今天过得如何？"
        "你好，今天怎么样？": "嘿，今天过得如何？",
        # Change "我很好，谢谢关心！你呢？" to "我挺好的，多谢关心！你咋样？"
        "我很好，谢谢关心！你呢？": "我挺好的，多谢关心！你咋样？",
        # Change "还不错！最近工作挺忙的。" to "还可以！最近工作特别忙。"
        "还不错！最近工作挺忙的。": "还可以！最近工作特别忙。",
    }

    # Apply edits to content
    for old_text, new_text in mock_edits.items():
        content = content.replace(old_text, new_text)

    # Write back
    doc_path.write_text(content, encoding='utf-8')

    console.print(f"[green]Applied {len(mock_edits)} mock edits to document[/green]")
    for old, new in mock_edits.items():
        console.print(f"  - '{old}' -> '{new}'")

    return mock_edits


def backfill_to_database(db: Session, episode: Episode) -> list[Diff]:
    """Backfill Obsidian edits to database."""
    console = Console()

    console.print("\n[bold yellow]Step 3: Backfilling Edits to Database[/bold yellow]")

    publisher = WorkflowPublisher(db, Console())
    diffs = publisher.parse_and_backfill(episode)

    console.print(f"[green]Backfilled {len(diffs)} changes to database[/green]")

    # Display diffs
    if diffs:
        diffs_table = Table(title="Backfilled Changes", show_header=True)
        diffs_table.add_column("Cue ID", style="cyan")
        diffs_table.add_column("Field", style="yellow")
        diffs_table.add_column("Original", style="red")
        diffs_table.add_column("New", style="green")

        for diff in diffs:
            diffs_table.add_row(
                str(diff.cue_id),
                diff.field,
                diff.original_value[:30] + "..." if len(diff.original_value) > 30 else diff.original_value,
                diff.new_value[:30] + "..." if len(diff.new_value) > 30 else diff.new_value
            )

        console.print(diffs_table)

    return diffs


def verify_database_state(db: Session, episode: Episode):
    """Verify and display final database state."""
    console = Console()

    console.print("\n[bold yellow]Step 4: Verifying Database State[/bold yellow]")

    # Get updated cues and translations
    cues = db.query(TranscriptCue).join(AudioSegment).filter(
        AudioSegment.episode_id == episode.id
    ).order_by(TranscriptCue.start_time).all()

    edited_count = 0
    final_table = Table(title="Final Database State", show_header=True)
    final_table.add_column("Cue ID", style="cyan")
    final_table.add_column("Time", style="dim")
    final_table.add_column("Translation", style="green")
    final_table.add_column("Is Edited", justify="center")

    for cue in cues:
        translation = cue.translations[0] if cue.translations else None
        if translation and translation.is_edited:
            edited_count += 1

        time_str = f"{cue.start_time:.1f}s"
        is_edited = "[green]✓[/green]" if translation and translation.is_edited else "[dim]✗[/dim]"
        trans_text = translation.translation[:40] + "..." if translation and len(translation.translation) > 40 else (translation.translation if translation else "-")

        final_table.add_row(str(cue.id), time_str, trans_text, is_edited)

    console.print(final_table)
    console.print(f"\n[bold]Summary:[/bold] {edited_count} translations marked as edited")


def main():
    """Main test function."""
    console = Console()

    console.print(Panel.fit("[bold cyan]Workflow Integration Test: Obsidian Edit & Backfill[/bold cyan]"))
    console.print("[dim]This test simulates the complete workflow of:[/dim]")
    console.print("[dim]1. Creating mock episode with transcription data[/dim]")
    console.print("[dim]2. Generating Obsidian document[/dim]")
    console.print("[dim]3. Simulating manual edits[/dim]")
    console.print("[dim]4. Parsing and backfilling changes to database[/dim]")

    # Configuration
    obsidian_path = Path(r"D:\programming_enviroment\EnglishPod-knowledgeBase\backend\data\obsidian_vault")
    obsidian_path.mkdir(parents=True, exist_ok=True)

    # Use in-memory database
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)

    global db
    db = Session(engine)

    try:
        # Step 0: Create mock episode
        console.print("\n[bold yellow]Step 0: Creating Mock Episode[/bold yellow]")
        episode = create_mock_episode_with_data(db)
        display_episode_data(console, episode)

        # Step 1: Generate Obsidian document
        doc_path = generate_obsidian_document(db, episode, obsidian_path)

        # Step 2: Parse original document
        original_data = parse_obsidian_document(db, episode, obsidian_path)

        # Step 3: Simulate manual edits
        mock_edits = simulate_manual_edit(doc_path)

        # Step 4: Backfill changes to database
        diffs = backfill_to_database(db, episode)

        # Step 5: Verify final state
        verify_database_state(db, episode)

        # Summary
        console.print("\n[bold green]Test Complete![/bold green]")
        console.print(Panel.fit(
            f"""Episode ID: {episode.id}
Title: {episode.title}
Document: {doc_path}
Edits Applied: {len(mock_edits)}
Changes Backfilled: {len(diffs)}"""
        ))

        console.print("\n[dim]Tip: You can manually edit the Obsidian document at:[/dim]")
        console.print(f"[dim]{doc_path}[/dim]")
        console.print("[dim]Then run the parse_and_backfill function again to test real edits.[/dim]")

    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        import traceback
        console.print(traceback.format_exc())
    finally:
        db.close()


if __name__ == "__main__":
    main()
