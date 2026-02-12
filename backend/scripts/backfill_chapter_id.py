"""
Chapter ID Backfill Script

回填 TranscriptCue.chapter_id 字段，根据时间范围将 cues 分配到对应的 chapters。

使用方法:
    # 单个 episode (dry-run)
    python scripts/backfill_chapter_id.py --episode-id 19 --dry-run

    # 单个 episode (执行)
    python scripts/backfill_chapter_id.py --episode-id 19

    # 批量处理 (限制数量)
    python scripts/backfill_chapter_id.py --limit 5

    # 强制重新分配
    python scripts/backfill_chapter_id.py --episode-id 19 --force

    # 指定多个 episodes
    python scripts/backfill_chapter_id.py --episode-ids 19,20,21
"""
import argparse
import logging
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import get_session
from app.services.chapter_id_backfill import ChapterIdBackfiller, BackfillStats

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_stats(stats: BackfillStats, verbose: bool = False):
    """打印统计信息"""
    print(f"\n{'='*60}")
    print(f"Episode {stats.episode_id} 回填统计")
    print(f"{'='*60}")
    print(f"  总 cues 数:      {stats.total_cues}")
    print(f"  新分配:          {stats.assigned_cues}")
    print(f"  重新分配:        {stats.reassigned_cues}")
    print(f"  跳过:            {stats.skipped_cues}")
    print(f"  范围外:          {stats.out_of_range_cues}")
    print(f"  回填前 NULL:     {stats.null_chapter_before}")
    print(f"  回填后 NULL:     {stats.null_chapter_after}")

    if stats.chapter_issues and verbose:
        print(f"\n  章节数据问题:")
        for issue in stats.chapter_issues:
            print(f"    - {issue}")
    print(f"{'='*60}\n")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="回填 chapter_id 到 TranscriptCue",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--episode-id",
        type=int,
        help="指定单个 Episode ID"
    )
    parser.add_argument(
        "--episode-ids",
        type=str,
        help="指定多个 Episode ID (逗号分隔，例如: 19,20,21)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="限制处理的 Episode 数量（用于批量测试）"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只显示将要更改的内容，不实际执行"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重新分配（纠正错误的chapter_id）"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="显示详细信息（包括章节数据问题）"
    )

    args = parser.parse_args()

    # 验证参数
    if args.episode_id and args.episode_ids:
        logger.error("--episode-id 和 --episode-ids 不能同时使用")
        return 1

    if args.episode_ids:
        episode_ids = [int(x.strip()) for x in args.episode_ids.split(",")]
    else:
        episode_ids = None

    # 执行回填
    with get_session() as session:
        backfiller = ChapterIdBackfiller(session)

        if args.episode_id:
            # 处理单个 episode
            logger.info(f"开始处理 episode {args.episode_id} (dry_run={args.dry_run}, force={args.force})")
            stats = backfiller.backfill_episode(
                args.episode_id,
                dry_run=args.dry_run,
                force=args.force
            )
            print_stats(stats, verbose=args.verbose)

        else:
            # 批量处理
            logger.info(f"开始批量处理 (limit={args.limit}, episode_ids={episode_ids}, dry_run={args.dry_run}, force={args.force})")

            all_stats = backfiller.backfill_all_episodes(
                limit=args.limit,
                episode_ids=episode_ids,
                dry_run=args.dry_run,
                force=args.force
            )

            # 打印总体统计
            total_episodes = len(all_stats)
            total_cues = sum(s.total_cues for s in all_stats)
            total_assigned = sum(s.assigned_cues for s in all_stats)
            total_reassigned = sum(s.reassigned_cues for s in all_stats)
            total_skipped = sum(s.skipped_cues for s in all_stats)
            total_out_of_range = sum(s.out_of_range_cues for s in all_stats)
            episodes_with_issues = [s for s in all_stats if s.chapter_issues]

            print(f"\n{'='*60}")
            print("批量回填总体统计")
            print(f"{'='*60}")
            print(f"  处理 episodes:  {total_episodes}")
            print(f"  总 cues 数:      {total_cues}")
            print(f"  总新分配:        {total_assigned}")
            print(f"  总重新分配:      {total_reassigned}")
            print(f"  总跳过:          {total_skipped}")
            print(f"  总范围外:        {total_out_of_range}")

            if episodes_with_issues and args.verbose:
                print(f"\n  有章节数据问题的 episodes:")
                for stats in episodes_with_issues:
                    print(f"    Episode {stats.episode_id}:")
                    for issue in stats.chapter_issues:
                        print(f"      - {issue}")
            print(f"{'='*60}\n")

            # 打印每个 episode 的详细统计
            if args.verbose:
                for stats in all_stats:
                    print_stats(stats, verbose=True)

        if args.dry_run:
            print("注意: 这是 dry-run 模式，没有实际更改数据库")

    return 0


if __name__ == "__main__":
    sys.exit(main())
