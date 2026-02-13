#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查询生产库 episode 21 的 marketing_posts"""
import sqlite3
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
DB_CANDIDATES = [
    BACKEND / "knowledge_base.db",
    BACKEND / "data" / "episodes.db",
    BACKEND / "data" / "knowledge_base.db",
]


def main():
    episode_id = int(sys.argv[1]) if len(sys.argv) > 1 else 21
    for db_path in DB_CANDIDATES:
        if not db_path.exists():
            continue
        conn = sqlite3.connect(str(db_path))
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='marketing_posts'"
        )
        if not cur.fetchone():
            conn.close()
            continue
        cur = conn.execute(
            "SELECT id, episode_id, angle_tag, title, content FROM marketing_posts WHERE episode_id = ?",
            (episode_id,),
        )
        rows = cur.fetchall()
        conn.close()
        print(f"数据库: {db_path}")
        print(f"Episode {episode_id} 营销文案数量: {len(rows)}")
        for r in rows:
            print(f"  ID={r[0]} angle_tag={r[2]}")
            print(f"    title: {(r[3] or '')[:80]}")
            print(f"    content_preview: {(r[4] or '')[:150]}...")
        return 0
    print("未找到含 marketing_posts 表的数据库")
    return 1


if __name__ == "__main__":
    sys.exit(main())
