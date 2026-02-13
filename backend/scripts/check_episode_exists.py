#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查 Episode 是否存在（不依赖 config.yaml，直接查 SQLite）
用法: python scripts/check_episode_exists.py [episode_id] [db_path]
"""
import sqlite3
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
DB_CANDIDATES = [
    BACKEND / "knowledge_base.db",
    BACKEND / "data" / "episodes.db",
    BACKEND / "data" / "knowledge_base.db",
]


def check(episode_id: int, db_path: Path):
    """返回 (id, title) 若存在，否则 None"""
    if not db_path.exists():
        return "no_file"
    conn = sqlite3.connect(str(db_path))
    cur = conn.execute("SELECT id, title FROM episodes WHERE id = ?", (episode_id,))
    row = cur.fetchone()
    conn.close()
    return row


def main():
    episode_id = int(sys.argv[1]) if len(sys.argv) > 1 else 19
    db_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    if db_path:
        paths = [db_path]
    else:
        paths = DB_CANDIDATES

    result_lines = []
    for p in paths:
        row = check(episode_id, p)
        if row == "no_file":
            continue
        result_lines.append(f"数据库: {p}")
        if row:
            result_lines.append(f"Episode {episode_id} 存在: {row[1]}")
        else:
            result_lines.append(f"Episode {episode_id} 不存在（已删除或从未存在）")
        result = "\n".join(result_lines)
        print(result)
        (BACKEND / "check_episode_result.txt").write_text(result, encoding="utf-8")
        return 0

    result = "未找到数据库文件，尝试路径: " + str([str(p) for p in paths])
    print(result)
    (BACKEND / "check_episode_result.txt").write_text(result, encoding="utf-8")
    return 1


if __name__ == "__main__":
    sys.exit(main())
