"""
Review Status Service - 审核状态管理服务

负责：
1. 检测 Obsidian 文档的审核状态变化
2. 将用户审核结果回填到数据库
3. 触发发布流程
"""
import logging
import re
from pathlib import Path
from typing import List, Optional, Dict
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Episode
from app.config import OBSIDIAN_VAULT_PATH, OBSIDIAN_NOTES_SUBDIR
from app.services.obsidian_service import ObsidianService
from app.enums.workflow_status import WorkflowStatus

logger = logging.getLogger(__name__)


@dataclass
class ReviewStatus:
    """审核状态"""
    episode_id: int
    status: str  # pending_review, approved, rejected
    file_path: Path


class ReviewService:
    """
    审核状态管理服务

    工作流：
    1. 用户在 Obsidian 中修改 YAML Frontmatter 的 status 字段
    2. 系统扫描文件并检测状态变化
    3. 更新数据库 Episode.workflow_status
    """

    def __init__(self, db: Session, vault_path: Optional[str] = None):
        """
        初始化服务

        Args:
            db: 数据库会话
            vault_path: Obsidian Vault 路径
        """
        self.db = db
        self.vault_path = vault_path or OBSIDIAN_VAULT_PATH
        self.notes_dir = Path(self.vault_path) / OBSIDIAN_NOTES_SUBDIR

    def scan_review_status(self) -> List[ReviewStatus]:
        """
        扫描所有 Obsidian 文档的审核状态

        Returns:
            List[ReviewStatus]: 所有文档的审核状态
        """
        if not self.notes_dir.exists():
            logger.warning(f"Obsidian 目录不存在: {self.notes_dir}")
            return []

        statuses = []

        for md_file in self.notes_dir.glob("*.md"):
            try:
                status = self._parse_review_status(md_file)
                if status:
                    statuses.append(status)
            except Exception as e:
                logger.error(f"解析文件失败 {md_file}: {e}")

        return statuses

    def _parse_review_status(self, file_path: Path) -> Optional[ReviewStatus]:
        """
        解析单个文件的审核状态

        Args:
            file_path: Markdown 文件路径

        Returns:
            Optional[ReviewStatus]: 审核状态，解析失败返回 None
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 提取 episode_id
        episode_id_match = re.search(r'task_id:\s*(\d+)', content)
        if not episode_id_match:
            return None

        episode_id = int(episode_id_match.group(1))

        # 提取 status
        status_match = re.search(r'status:\s*(\w+)', content)
        if not status_match:
            return None

        status = status_match.group(1)

        return ReviewStatus(
            episode_id=episode_id,
            status=status,
            file_path=file_path
        )

    def sync_approved_episodes(self) -> int:
        """
        同步已审核通过的 Episode 到数据库

        将 status=approved 的 Episode 更新为 PUBLISHED 状态

        Returns:
            int: 更新的数量
        """
        statuses = self.scan_review_status()

        approved_episodes = [s for s in statuses if s.status == "approved"]

        if not approved_episodes:
            logger.info("没有已审核通过的 Episode")
            return 0

        count = 0
        for review_status in approved_episodes:
            episode = self.db.query(Episode).filter(
                Episode.id == review_status.episode_id
            ).first()

            if episode:
                episode.workflow_status = WorkflowStatus.PUBLISHED.value
                count += 1
                logger.info(f"Episode {episode.id} 标记为已发布")

        self.db.commit()
        return count

    def check_episode_approved(self, episode_id: int) -> bool:
        """
        检查指定 Episode 是否已审核通过

        Args:
            episode_id: Episode ID

        Returns:
            bool: 是否已审核通过
        """
        episode = self.db.query(Episode).filter(Episode.id == episode_id).first()
        if not episode:
            return False

        # 查找对应的 Obsidian 文件
        md_files = list(self.notes_dir.glob(f"{episode_id}-*.md"))
        if not md_files:
            return False

        md_file = md_files[0]

        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 检查 status 是否为 approved
        status_match = re.search(r'status:\s*approved', content)
        return status_match is not None

    def get_pending_review_episodes(self) -> List[Episode]:
        """
        获取待审核的 Episode 列表

        Returns:
            List[Episode]: 待审核的 Episode
        """
        return self.db.query(Episode).filter(
            Episode.workflow_status == WorkflowStatus.READY_FOR_REVIEW.value
        ).all()

    def print_review_summary(self):
        """打印审核状态摘要"""
        pending = self.get_pending_review_episodes()
        statuses = self.scan_review_status()

        approved_count = sum(1 for s in statuses if s.status == "approved")
        pending_count = sum(1 for s in statuses if s.status == "pending_review")

        print(f"\n{'='*60}")
        print(f"审核状态摘要")
        print(f"{'='*60}")
        print(f"数据库中待审核: {len(pending)} 个 Episode")
        print(f"Obsidian 中待审核: {pending_count} 个文档")
        print(f"Obsidian 中已通过: {approved_count} 个文档")
        print(f"{'='*60}\n")
