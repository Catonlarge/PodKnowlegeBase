"""
数据迁移脚本：添加 APPROVED 状态

变更内容：
- 原状态: INIT(0) → DOWNLOADED(1) → ... → READY_FOR_REVIEW(6) → PUBLISHED(7)
- 新状态: INIT(0) → DOWNLOADED(1) → ... → READY_FOR_REVIEW(6) → APPROVED(7) → PUBLISHED(8)

迁移操作：
1. 将所有 workflow_status = 7 (PUBLISHED) 的 Episode 更新为 8 (PUBLISHED)
2. 验证迁移结果
"""
import sys
from pathlib import Path

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import get_session
from app.models import Episode
from app.enums.workflow_status import WorkflowStatus


def migrate():
    """执行数据迁移"""
    print("=" * 70)
    print("数据迁移：添加 APPROVED 状态")
    print("=" * 70)

    with get_session() as db:
        # 查询当前所有 PUBLISHED (7) 状态的 Episode
        old_published_episodes = db.query(Episode).filter(
            Episode.workflow_status == 7
        ).all()

        print(f"\n找到 {len(old_published_episodes)} 个状态为 PUBLISHED(7) 的 Episode")

        if not old_published_episodes:
            print("没有需要迁移的数据")
            return

        # 显示将要迁移的 Episode
        print("\n将要迁移的 Episode:")
        for ep in old_published_episodes[:10]:
            print(f"  - ID: {ep.id}, Title: {ep.title[:50]}...")
        if len(old_published_episodes) > 10:
            print(f"  ... 还有 {len(old_published_episodes) - 10} 个")

        # 执行迁移
        print("\n执行迁移...")
        for episode in old_published_episodes:
            episode.workflow_status = 8  # 新的 PUBLISHED 状态值

        db.commit()

        print(f"[OK] Migration completed: {len(old_published_episodes)} episodes")
        print("  7 (old PUBLISHED) -> 8 (new PUBLISHED)")

        # 验证迁移结果
        print("\nVerifying migration...")
        new_published_episodes = db.query(Episode).filter(
            Episode.workflow_status == 8
        ).all()

        print(f"[OK] Verification passed: {len(new_published_episodes)} episodes with status PUBLISHED(8)")

        # 检查是否有遗漏
        remaining_old = db.query(Episode).filter(
            Episode.workflow_status == 7
        ).count()

        if remaining_old > 0:
            print(f"[WARNING] Still have {remaining_old} episodes with status 7")
        else:
            print("[OK] All old status migrated")

        # 显示当前状态分布
        print("\n当前状态分布:")
        for status in WorkflowStatus:
            count = db.query(Episode).filter(
                Episode.workflow_status == status.value
            ).count()
            if count > 0:
                print(f"  {status.label} ({status.value}): {count}")

    print("\n" + "=" * 70)
    print("数据迁移完成")
    print("=" * 70)


if __name__ == "__main__":
    migrate()
