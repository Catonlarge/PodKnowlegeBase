"""
章节切分预览脚本

调用真实 LLM 进行章节分析，输出 MD 文档供审核。
不写入数据库，仅预览大模型返回结果。

用法:
    python scripts/preview_segmentation_episode19.py [--episode-id 21]
    python scripts/preview_segmentation_episode19.py 21

输出:
    backend/tests/test_data/episode_<id>_segmentation_preview_YYYYMMDD_HHMMSS.md
"""
import argparse
import sys
import os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from app.database import init_database, get_session
from app.config import BASE_DIR
from app.models.base import Base
from app.services.segmentation_service import SegmentationService

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "tests" / "test_data"


def _format_timestamp(seconds: float) -> str:
    """秒数转为 MM:SS 格式"""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def main():
    parser = argparse.ArgumentParser(description="章节切分预览（调用 LLM，不写入数据库）")
    parser.add_argument("episode_id", nargs="?", type=int, default=21, help="Episode ID（默认 21）")
    parser.add_argument("--test-db", action="store_true", help="使用测试数据库 episodes_test.db")
    args = parser.parse_args()
    episode_id = args.episode_id

    init_database()
    if args.test_db:
        import app.database as db_module
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        test_db_path = BASE_DIR / "data" / "episodes_test.db"
        test_db_path.parent.mkdir(parents=True, exist_ok=True)
        test_engine = create_engine(
            f"sqlite:///{test_db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
        db_module._session_factory = sessionmaker(
            bind=test_engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
        Base.metadata.create_all(test_engine)
        print(f"使用测试数据库: {test_db_path}")
    output_dir = OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"episode_{episode_id}_segmentation_preview_{timestamp}.md"

    print(f"Episode {episode_id} 章节切分预览")
    print(f"输出: {output_path}")
    print("-" * 60)

    with get_session() as db:
        service = SegmentationService(db, provider="moonshot")
        if not service.structured_llm:
            print("错误: StructuredLLM 未初始化，请检查 MOONSHOT_API_KEY")
            sys.exit(1)

        result = service.preview_segmentation(episode_id, for_preview=True)

    chapters = result["chapters"]
    step1_reasoning = result.get("step1_reasoning", "")

    lines = [
        f"# Episode {episode_id} 章节切分预览（大模型输出）",
        "",
        f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"章节数: {len(chapters)}",
        "",
        "---",
        "",
    ]
    if step1_reasoning:
        lines.extend([
            "## 第一步：章节划分与时间戳范围",
            "",
            f"> **step1_reasoning**: {step1_reasoning}",
            "",
            "---",
            "",
        ])
    lines.extend([
        "## 第二步：各章节标题与推导思路",
        "",
    ])

    for i, ch in enumerate(chapters, 1):
        start_ts = _format_timestamp(ch["start_time"])
        end_ts = _format_timestamp(ch["end_time"])
        start_s = int(ch["start_time"])
        end_s = int(ch["end_time"])
        duration_min = (ch["end_time"] - ch["start_time"]) / 60
        reasoning = ch.get("reasoning", "")

        lines.extend([
            f"### 章节 {i}: [{start_ts}] {ch['title']}",
            "",
            f"> **摘要**: {ch['summary']}",
            "",
            f"**时间范围**: {start_s}s - {end_s}s ({start_ts} - {end_ts})",
            f"**时长**: {duration_min:.1f} 分钟",
            "",
        ])
        if reasoning:
            lines.extend([
                f"**推导思路 (CoT)**: {reasoning}",
                "",
            ])
        lines.extend([
            "---",
            "",
        ])

    content = "\n".join(lines)
    output_path.write_text(content, encoding="utf-8")

    print(f"完成，共 {len(chapters)} 个章节")
    print(f"已保存: {output_path}")
    for i, ch in enumerate(chapters, 1):
        start_ts = _format_timestamp(ch["start_time"])
        end_ts = _format_timestamp(ch["end_time"])
        print(f"  {i}. [{start_ts}-{end_ts}] {ch['title']}")


if __name__ == "__main__":
    main()
