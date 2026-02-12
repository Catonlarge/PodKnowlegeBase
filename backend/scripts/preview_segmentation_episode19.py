"""
Episode 19 章节切分预览脚本

调用真实 LLM 进行章节分析，输出 MD 文档供审核。
不写入数据库，仅预览大模型返回结果。

用法:
    python scripts/preview_segmentation_episode19.py

输出:
    backend/tests/test_data/episode_19_segmentation_preview_YYYYMMDD_HHMMSS.md
"""
import sys
import os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from app.database import init_database, get_session
from app.services.segmentation_service import SegmentationService

EPISODE_ID = 19
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "tests" / "test_data"


def _format_timestamp(seconds: float) -> str:
    """秒数转为 MM:SS 格式"""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def main():
    init_database()
    output_dir = OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"episode_19_segmentation_preview_{timestamp}.md"

    print(f"Episode {EPISODE_ID} 章节切分预览")
    print(f"输出: {output_path}")
    print("-" * 60)

    with get_session() as db:
        service = SegmentationService(db, provider="moonshot")
        if not service.structured_llm:
            print("错误: StructuredLLM 未初始化，请检查 MOONSHOT_API_KEY")
            sys.exit(1)

        chapters = service.preview_segmentation(EPISODE_ID)

    lines = [
        "# Episode 19 章节切分预览（大模型输出）",
        "",
        f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"章节数: {len(chapters)}",
        "",
        "---",
        "",
        "## 章节概览（含时间戳，用于核对标题与内容对应）",
        "",
    ]

    for i, ch in enumerate(chapters, 1):
        start_ts = _format_timestamp(ch["start_time"])
        end_ts = _format_timestamp(ch["end_time"])
        start_s = int(ch["start_time"])
        end_s = int(ch["end_time"])
        duration_min = (ch["end_time"] - ch["start_time"]) / 60

        lines.extend([
            f"### 章节 {i}: [{start_ts}] {ch['title']}",
            "",
            f"> **摘要**: {ch['summary']}",
            "",
            f"**时间范围**: {start_s}s - {end_s}s ({start_ts} - {end_ts})",
            f"**时长**: {duration_min:.1f} 分钟",
            "",
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
