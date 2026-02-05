"""
Real AI Integration Test for SubtitleProofreadingService

This script tests the SubtitleProofreadingService with real Moonshot API calls.
It loads an SRT file, creates database records, calls LLM for proofreading,
and reports the results.
"""
import re
import sys
import os
from pathlib import Path

# Fix encoding for Windows console
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set minimal environment variables if not already set
# This allows the script to run without full environment setup
if not os.environ.get("HF_TOKEN"):
    os.environ["HF_TOKEN"] = "test_token_for_proofreading"
if not os.environ.get("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = "test_key_for_proofreading"
if not os.environ.get("ZHIPU_API_KEY"):
    os.environ["ZHIPU_API_KEY"] = "test_key_for_proofreading"

# Use a separate test database to avoid affecting real data
os.environ["DATABASE_PATH"] = "./data/test_proofreading.db"

from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.services.subtitle_proofreading_service import SubtitleProofreadingService
from app.models import Episode, AudioSegment, TranscriptCue, TranscriptCorrection
from app.models.base import Base


def create_test_session() -> Session:
    """
    Create an in-memory SQLite database session for testing.

    Returns:
        Session: SQLAlchemy session
    """
    # Create in-memory database
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    # Create all tables with latest schema
    Base.metadata.create_all(engine)

    # Create session factory
    SessionFactory = sessionmaker(bind=engine)
    return SessionFactory()


def parse_srt_time(time_str: str) -> float:
    """
    Convert SRT timestamp to seconds.

    Args:
        time_str: SRT timestamp like "00:00:00,031"

    Returns:
        float: Time in seconds
    """
    # Parse "00:00:00,031" format
    match = re.match(r'(\d+):(\d+):(\d+),(\d+)', time_str.strip())
    if match:
        hours, minutes, seconds, milliseconds = map(int, match.groups())
        return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000
    return 0.0


def parse_srt_file(srt_path: str) -> list:
    """
    Parse SRT file into list of subtitle entries.

    Args:
        srt_path: Path to SRT file

    Returns:
        list of dict: Each with index, start_time, end_time, speaker, text
    """
    with open(srt_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split by double newlines to get individual subtitle blocks
    blocks = re.split(r'\n\s*\n', content.strip())

    entries = []
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            # First line is subtitle index
            index = int(lines[0].strip())

            # Second line is timestamp range
            time_match = re.match(r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})', lines[1])
            if time_match:
                start_time = parse_srt_time(time_match.group(1))
                end_time = parse_srt_time(time_match.group(2))

                # Remaining lines are the subtitle text
                text = '\n'.join(lines[2:])

                # Extract speaker from [SPEAKER_XX] pattern
                speaker_match = re.search(r'\[SPEAKER_(\d+)\]', text)
                if speaker_match:
                    speaker = f"SPEAKER_{speaker_match.group(1)}"
                    # Remove the speaker tag from text
                    text = re.sub(r'\[SPEAKER_\d+\]\s*', '', text)
                else:
                    speaker = "SPEAKER_UNKNOWN"

                entries.append({
                    'index': index,
                    'start_time': start_time,
                    'end_time': end_time,
                    'speaker': speaker,
                    'text': text.strip()
                })

    return entries


def setup_test_data(db: Session, srt_entries: list) -> int:
    """
    Create test Episode, AudioSegment, and TranscriptCue records.

    Args:
        db: Database session
        srt_entries: Parsed SRT entries

    Returns:
        int: Episode ID
    """
    # Create episode
    episode = Episode(
        title="Figma Products Discussion - Proofreading Test",
        file_hash="proofread_test_016",
        duration=max(e['end_time'] for e in srt_entries),
        workflow_status=2,  # TRANSCRIBED
    )
    db.add(episode)
    db.flush()

    # Create a single audio segment for all cues
    segment = AudioSegment(
        episode_id=episode.id,
        segment_index=0,
        segment_id="seg_001",
        start_time=0.0,
        end_time=episode.duration
    )
    db.add(segment)
    db.flush()

    # Create transcript cues from SRT entries
    for entry in srt_entries:
        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=entry['start_time'],
            end_time=entry['end_time'],
            speaker=entry['speaker'],
            text=entry['text']
        )
        db.add(cue)

    db.commit()
    print(f"Created Episode {episode.id} with {len(srt_entries)} transcript cues")

    return episode.id


def print_correction_report(result, original_entries):
    """
    Print a detailed report of the proofreading results.

    Args:
        result: CorrectionResult from service
        original_entries: Original SRT entries for reference
    """
    print("\n" + "="*80)
    print("SUBTITLE PROOFREADING REPORT")
    print("="*80)

    print(f"\n📊 SUMMARY:")
    print(f"  Total cues processed: {result.total_cues}")
    print(f"  Corrections found: {result.corrected_count}")
    print(f"  Skipped (already corrected): {result.skipped_count}")
    print(f"  Duration: {result.duration_seconds:.2f} seconds")

    if result.corrections:
        print(f"\n🔍 CORRECTIONS FOUND ({len(result.corrections)}):")
        print("-"*80)

        for i, correction in enumerate(result.corrections, 1):
            # Find original entry for context
            original_text = correction.original_text

            print(f"\n{i}. Cue ID {correction.cue_id}")
            print(f'   Original:  "{original_text}"')
            print(f'   Corrected: "{correction.corrected_text}"')
            print(f"   Reason:    {correction.reason}")
            print(f"   Confidence: {correction.confidence:.2%}")

            # Show diff
            original_words = original_text.split()
            corrected_words = correction.corrected_text.split()
            if original_words != corrected_words:
                print(f"   Diff:      ", end="")
                for j, (orig, corr) in enumerate(zip(original_words, corrected_words)):
                    if orig != corr:
                        print(f"[{orig}→{corr}]", end=" ")
                    elif j < len(original_words) - 1 or len(corrected_words) == len(original_words):
                        print(orig, end=" ")
                # Handle trailing words
                if len(corrected_words) > len(original_words):
                    for word in corrected_words[len(original_words):]:
                        print(f"+{word}", end=" ")
                print()
    else:
        print("\n✅ No corrections found - subtitles look good!")

    print("\n" + "="*80)


def main():
    """Main test function."""
    print("="*80)
    print("Subtitle Proofreading Service - Real AI Integration Test")
    print("="*80)

    # Path to SRT file
    srt_path = r"D:\programming_enviroment\learning-EnglishPod3\docs\016_analysis\016_subtitles_original.srt"

    if not os.path.exists(srt_path):
        print(f"ERROR: SRT file not found: {srt_path}")
        return

    print(f"\n📂 Loading SRT file: {srt_path}")

    # Parse SRT file
    entries = parse_srt_file(srt_path)
    print(f"✅ Parsed {len(entries)} subtitle entries")

    # Show first few entries as preview
    print("\n📝 Preview of first 3 entries:")
    for i, entry in enumerate(entries[:3], 1):
        print(f"  {i}. [{entry['speaker']}] {entry['text'][:60]}...")

    # Setup database
    print("\n💾 Creating test database records...")
    db = create_test_session()

    try:
        episode_id = setup_test_data(db, entries)

        # Initialize service with real LLM
        print("\n🤖 Initializing SubtitleProofreadingService with Moonshot API...")
        service = SubtitleProofreadingService(db)

        # Run proofreading (dry run first)
        print("\n🔍 Scanning for corrections (dry run, not applying)...")
        result = service.scan_and_correct(
            episode_id=episode_id,
            batch_size=20,
            apply=False  # Don't apply yet
        )

        # Print report
        print_correction_report(result, entries)

        # Apply corrections automatically
        if result.corrections:
            print("\n" + "="*80)
            print("\n💾 Applying corrections to database...")
            applied = service.apply_corrections(result.corrections)

            # Verify corrections were applied
            cues = db.query(TranscriptCue).join(
                AudioSegment, TranscriptCue.segment_id == AudioSegment.id
            ).filter(
                AudioSegment.episode_id == episode_id,
                TranscriptCue.is_corrected == True
            ).all()

            print(f"✅ Applied {applied} corrections")
            print(f"✅ Verified {len(cues)} cues marked as corrected")

            # Show some examples of corrected text
            print("\n📋 Examples of corrected cues:")
            for i, cue in enumerate(cues[:5], 1):
                print(f"\n  {i}. Cue {cue.id}:")
                print(f"     Original:  {cue.text}")
                print(f"     Corrected: {cue.corrected_text}")

            # Export corrected SRT file
            output_dir = Path(srt_path).parent
            corrected_srt_path = output_dir / "016_subtitles_corrected.srt"
            print(f"\n📄 Exporting corrected subtitles to:")
            print(f"   {corrected_srt_path}")
            exported = service.export_corrected_srt(episode_id, str(corrected_srt_path))
            print(f"✅ Exported {exported} subtitle entries")
        else:
            print("\n✅ No corrections to apply")
    finally:
        db.close()

        print("\n" + "="*80)
        print("Test completed!")
        print("="*80)


if __name__ == "__main__":
    main()
