"""
Chapter ID Verification Script

验证 TranscriptCue.chapter_id 分配是否正确。

使用方法:
    # 验证单个 episode
    python scripts/verify_chapter_id.py --episode-id 19

    # 验证所有 episodes
    python scripts/verify_chapter_id.py --all

    # 显示详细信息
    python scripts/verify_chapter_id.py --episode-id 19 --verbose

    # 输出格式化报告
    python scripts/verify_chapter_id.py --episode-id 19 --report
"""
import argparse
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import get_session
from app.models import Episode, Chapter, TranscriptCue, AudioSegment
from sqlalchemy import func

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class VerificationReport:
    """验证报告"""
    episode_id: int
    total_cues: int = 0
    null_chapter_id: int = 0
    mismatched_cues: int = 0
    correct_cues: int = 0
    out_of_range_cues: int = 0
    chapters: List[Dict] = None

    def __post_init__(self):
        if self.chapters is None:
            self.chapters = []


def verify_episode(session, episode_id: int, verbose: bool = False) -> VerificationReport:
    """
    验证单个 episode 的 chapter_id 分配

    Args:
        session: 数据库会话
        episode_id: Episode ID
        verbose: 是否显示详细信息

    Returns:
        VerificationReport: 验证报告
    """
    report = VerificationReport(episode_id=episode_id)

    # 获取所有 chapters
    chapters = session.query(Chapter).filter(
        Chapter.episode_id == episode_id
    ).order_by(Chapter.start_time).all()

    if not chapters:
        logger.warning(f"Episode {episode_id} 没有章节数据")
        return report

    # 获取所有 cues
    cues = session.query(TranscriptCue).join(
        AudioSegment, TranscriptCue.segment_id == AudioSegment.id
    ).filter(
        AudioSegment.episode_id == episode_id
    ).order_by(TranscriptCue.start_time).all()

    report.total_cues = len(cues)

    # 验证每个 cue
    chapter_cue_counts = defaultdict(int)
    mismatched_details = []

    for cue in cues:
        # 统计 NULL
        if cue.chapter_id is None:
            report.null_chapter_id += 1
            continue

        # 找到应该分配的 chapter
        expected_chapter = None
        for chapter in chapters:
            if chapter.start_time <= cue.start_time < chapter.end_time:
                expected_chapter = chapter
                break

        # 处理范围外的 cues
        if expected_chapter is None:
            # 超出所有 chapters，应该分配给最后一个
            if cue.start_time >= chapters[-1].start_time:
                expected_chapter = chapters[-1]
                report.out_of_range_cues += 1
            else:
                # 不应该发生
                report.mismatched_cues += 1
                if verbose:
                    mismatched_details.append({
                        'cue_id': cue.id,
                        'start_time': cue.start_time,
                        'expected': None,
                        'actual': cue.chapter_id
                    })
                continue

        # 验证 chapter_id 是否正确
        if cue.chapter_id == expected_chapter.id:
            report.correct_cues += 1
            chapter_cue_counts[expected_chapter.chapter_index] += 1
        else:
            report.mismatched_cues += 1
            if verbose:
                mismatched_details.append({
                    'cue_id': cue.id,
                    'start_time': cue.start_time,
                    'expected': expected_chapter.id,
                    'expected_index': expected_chapter.chapter_index,
                    'actual': cue.chapter_id
                })

    # 构建章节数据
    for chapter in chapters:
        report.chapters.append({
            'index': chapter.chapter_index,
            'id': chapter.id,
            'start_time': chapter.start_time,
            'end_time': chapter.end_time,
            'cue_count': chapter_cue_counts.get(chapter.chapter_index, 0),
            'title': chapter.title
        })

    # 打印详细信息
    if verbose and mismatched_details:
        logger.info(f"Episode {episode_id} 发现 {len(mismatched_details)} 个不匹配的 cues:")
        for detail in mismatched_details[:10]:  # 只显示前10个
            logger.info(f"  Cue {detail['cue_id']} (start_time={detail['start_time']}): "
                       f"expected chapter {detail.get('expected_index', detail.get('expected'))}, "
                       f"got {detail['actual']}")
        if len(mismatched_details) > 10:
            logger.info(f"  ... 还有 {len(mismatched_details) - 10} 个")

    return report


def print_report(report: VerificationReport, verbose: bool = False):
    """打印验证报告"""
    print(f"\n{'='*60}")
    print(f"Episode {report.episode_id} 验证报告")
    print(f"{'='*60}")
    print(f"  总 cues 数:      {report.total_cues}")
    print(f"  正确分配:        {report.correct_cues} ({100*report.correct_cues/report.total_cues if report.total_cues > 0 else 0:.1f}%)")
    print(f"  NULL chapter_id: {report.null_chapter_id}")
    print(f"  分配错误:        {report.mismatched_cues}")
    print(f"  范围外 cues:     {report.out_of_range_cues}")

    if verbose and report.chapters:
        print(f"\n  章节 cue 分布:")
        for ch in report.chapters:
            print(f"    Chapter {ch['index']} ({ch['start_time']}-{ch['end_time']}s): "
                  f"{ch['cue_count']} cues")
    print(f"{'='*60}\n")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="验证 chapter_id 分配是否正确",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--episode-id",
        type=int,
        help="指定单个 Episode ID"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="验证所有 episodes"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="限制处理的 Episode 数量"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="显示详细信息"
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="输出格式化报告"
    )

    args = parser.parse_args()

    # 验证参数
    if not args.episode_id and not args.all:
        logger.error("必须指定 --episode-id 或 --all")
        return 1

    with get_session() as session:
        if args.episode_id:
            # 验证单个 episode
            report = verify_episode(session, args.episode_id, verbose=args.verbose)
            print_report(report, verbose=args.verbose)

            # 返回状态码
            if report.mismatched_cues > 0 or report.null_chapter_id > 0:
                return 1
            return 0

        else:
            # 验证所有 episodes
            query = session.query(Episode.id).order_by(Episode.id)
            if args.limit:
                query = query.limit(args.limit)

            episode_ids = [row[0] for row in query.all()]
            logger.info(f"开始验证 {len(episode_ids)} 个 episodes")

            all_reports = []
            total_issues = 0

            for episode_id in episode_ids:
                report = verify_episode(session, episode_id, verbose=args.verbose)
                all_reports.append(report)

                if report.mismatched_cues > 0 or report.null_chapter_id > 0:
                    total_issues += 1

                if args.verbose or args.report:
                    print_report(report, verbose=args.verbose)

            # 打印总体统计
            total_episodes = len(all_reports)
            total_cues = sum(r.total_cues for r in all_reports)
            total_correct = sum(r.correct_cues for r in all_reports)
            total_null = sum(r.null_chapter_id for r in all_reports)
            total_mismatched = sum(r.mismatched_cues for r in all_reports)

            print(f"\n{'='*60}")
            print("总体验证统计")
            print(f"{'='*60}")
            print(f"  总 episodes:    {total_episodes}")
            print(f"  有问题的:       {total_issues}")
            print(f"  总 cues 数:     {total_cues}")
            print(f"  正确分配:       {total_correct} ({100*total_correct/total_cues if total_cues > 0 else 0:.1f}%)")
            print(f"  NULL:           {total_null}")
            print(f"  分配错误:       {total_mismatched}")
            print(f"{'='*60}\n")

            return 0 if total_issues == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
