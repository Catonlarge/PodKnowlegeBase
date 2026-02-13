#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check translation status for an episode. Usage: python check_translation_status.py [ep_id] [--test-db]"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import init_database, get_session
from app.config import BASE_DIR
from app.models import Episode, TranscriptCue, Translation, AudioSegment, Chapter


def check(db, ep_id: int):
    ep = db.get(Episode, ep_id)
    if not ep:
        print(f"Episode {ep_id} does not exist")
        return
    total_cues = (
        db.query(TranscriptCue.id)
        .join(AudioSegment, TranscriptCue.segment_id == AudioSegment.id)
        .filter(AudioSegment.episode_id == ep_id)
        .count()
    )
    trans_all = (
        db.query(Translation)
        .join(TranscriptCue)
        .join(AudioSegment)
        .filter(AudioSegment.episode_id == ep_id, Translation.language_code == "zh")
        .all()
    )
    completed = [t for t in trans_all if t.translation_status == "completed"]
    other_statuses = {}
    for t in trans_all:
        other_statuses[t.translation_status] = other_statuses.get(t.translation_status, 0) + 1
    print(f"Episode {ep_id}: {ep.title}")
    print(f"Workflow status: {ep.workflow_status}")
    print(f"Total cues: {total_cues}")
    print(f"Translation records: {len(trans_all)}")
    print(f"  completed: {len(completed)}")
    print(f"  by status: {other_statuses}")
    if completed:
        print("Sample (first 2):")
        for t in completed[:2]:
            text = (t.translation or "")[:60]
            print(f"  cue_id={t.cue_id}: {text}...")
    print(f"Completeness: {len(completed)}/{total_cues}" + (f" ({100*len(completed)/total_cues:.1f}%)" if total_cues else ""))

    chapters = db.query(Chapter).filter(Chapter.episode_id == ep_id).order_by(Chapter.start_time).all()
    print(f"Chapters: {len(chapters)}")
    if chapters:
        for ch in chapters[:3]:
            print(f"  - {ch.chapter_index + 1}: {ch.title[:40]}... (summary: {bool(ch.summary)})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("ep_id", type=int, nargs="?", default=1)
    parser.add_argument("--test-db", action="store_true", help="Use episodes_test.db")
    args = parser.parse_args()

    init_database()
    if args.test_db:
        import app.database as db_module
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.models.base import Base
        test_db_path = BASE_DIR / "data" / "episodes_test.db"
        engine = create_engine(f"sqlite:///{test_db_path}", connect_args={"check_same_thread": False})
        db_module._session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(engine)
        print(f"Using: {test_db_path}\n")

    with get_session() as db:
        check(db, args.ep_id)
