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

        执行步骤：
        1. 检测 Obsidian 中 status: approved 的文档
        2. 解析文档，比对用户修改
        3. 只更新用户修改过的翻译（设置 is_edited = TRUE）
        4. 更新 Episode.workflow_status = APPROVED (7)

        Returns:
            int: 同步的 Episode 数量
        """
        from app.services.obsidian_service import ObsidianService
        from app.models import Translation

        statuses = self.scan_review_status()
        approved_episodes = [s for s in statuses if s.status == "approved"]

        if not approved_episodes:
            logger.info("没有已审核通过的 Episode")
            return 0

        obsidian_service = ObsidianService(self.db, vault_path=None)
        count = 0
        total_edited = 0

        for review_status in approved_episodes:
            episode_id = review_status.episode_id
            episode = self.db.query(Episode).filter(Episode.id == episode_id).first()

            if not episode:
                logger.warning(f"Episode {episode_id} 不存在于数据库")
                continue

            # 只允许从 READY_FOR_REVIEW 状态同步
            if episode.workflow_status != WorkflowStatus.READY_FOR_REVIEW.value:
                logger.warning(
                    f"Episode {episode_id} 状态为 {episode.workflow_status}，"
                    f"预期状态为 {WorkflowStatus.READY_FOR_REVIEW.value}，跳过"
                )
                continue

            # 读取 Obsidian 文档
            obsidian_path = review_status.file_path
            try:
                with open(obsidian_path, 'r', encoding='utf-8') as f:
                    markdown = f.read()
            except Exception as e:
                logger.error(f"读取文件失败 {obsidian_path}: {e}")
                continue

            # 解析用户修改
            diff_results = obsidian_service.parse_episode_from_markdown(
                episode_id, markdown, language_code="zh"
            )

            # 只更新用户修改过的翻译
            edited_count = 0
            for diff in diff_results:
                if diff.is_edited:
                    translation = self.db.query(Translation).filter(
                        Translation.cue_id == diff.cue_id,
                        Translation.language_code == "zh"
                    ).first()

                    if translation and translation.translation != diff.edited:
                        # 保存原始翻译（如果还没有保存）
                        if translation.original_translation is None:
                            translation.original_translation = translation.translation

                        # 更新为用户修改版本
                        translation.translation = diff.edited
                        translation.is_edited = True
                        edited_count += 1

            # 更新状态为 APPROVED
            episode.workflow_status = WorkflowStatus.APPROVED.value
            count += 1
            total_edited += edited_count

            logger.info(
                f"Episode {episode_id} 同步完成: "
                f"状态 → APPROVED, 编辑条目数: {edited_count}"
            )

        self.db.commit()
        logger.info(f"同步完成: {count} 个 Episode, 总编辑条目数: {total_edited}")
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
