"""Check chapter times in database"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import get_session
from app.models import Chapter
from sqlalchemy import desc

with get_session() as s:
    chs = s.query(Chapter).order_by(desc(Chapter.id)).limit(6).all()
    for c in reversed(chs):
        print(f'Chapter {c.chapter_index+1}: start={c.start_time}s, end={c.end_time}s')
