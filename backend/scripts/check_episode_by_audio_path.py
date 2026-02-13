#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check if an episode (and its translations) exists for a given audio path in both prod and test DB."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from app.config import BASE_DIR


def check_db(db_path: Path, label: str, search_pattern: str):
    """Query a SQLite DB for episodes matching the audio path pattern."""
    if not db_path.exists():
        print(f"[{label}] DB file not found: {db_path}")
        return

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    with engine.connect() as conn:
        # Check episodes
        ep_rows = conn.execute(
            text("SELECT id, title, audio_path, workflow_status FROM episodes WHERE audio_path LIKE :pattern"),
            {"pattern": f"%{search_pattern}%"}
        ).fetchall()

        if not ep_rows:
            print(f"[{label}] No episodes found for pattern: {search_pattern}")
            return

        print(f"[{label}] Found {len(ep_rows)} episode(s):")
        for r in ep_rows:
            ep_id, title, audio_path, status = r
            print(f"  Episode ID: {ep_id}, title: {title}, status: {status}")
            print(f"  audio_path: {audio_path}")

            # Count transcript cues and translations
            cue_count = conn.execute(
                text("""
                    SELECT COUNT(*) FROM transcript_cues tc
                    JOIN audio_segments a ON tc.segment_id = a.id
                    WHERE a.episode_id = :ep_id
                """),
                {"ep_id": ep_id}
            ).scalar()

            trans_rows = conn.execute(
                text("""
                    SELECT COUNT(*), translation_status FROM translations t
                    JOIN transcript_cues tc ON t.cue_id = tc.id
                    JOIN audio_segments a ON tc.segment_id = a.id
                    WHERE a.episode_id = :ep_id AND t.language_code = 'zh'
                    GROUP BY translation_status
                """),
                {"ep_id": ep_id}
            ).fetchall()

            trans_total = sum(c for c, _ in trans_rows)
            trans_completed = next((c for c, s in trans_rows if s == "completed"), 0)

            print(f"  Transcript cues: {cue_count}")
            print(f"  Translations (zh): total={trans_total}, completed={trans_completed}")
            if trans_rows:
                for c, s in trans_rows:
                    print(f"    - {s}: {c}")
            print()


def main():
    search = "Why-AI-evals-are-the-hottest-new-skill"
    if len(sys.argv) > 1:
        search = sys.argv[1]

    prod_db = BASE_DIR / "data" / "episodes.db"
    test_db = BASE_DIR / "data" / "episodes_test.db"

    print("=" * 60)
    print(f"Searching for audio_path containing: {search}")
    print("=" * 60)

    check_db(prod_db, "PRODUCTION (episodes.db)", search)
    check_db(test_db, "TEST (episodes_test.db)", search)


if __name__ == "__main__":
    main()
