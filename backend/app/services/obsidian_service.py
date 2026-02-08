"""
Obsidian Service - Obsidian 文档生成和解析服务

负责在数据库和 Obsidian Markdown 文档之间进行双向同步：

渲染方向 (Database → Obsidian):
- render_episode(): 从数据库生成 Obsidian Markdown 文档
- save_episode(): 保存 Markdown 文件到 Obsidian Vault

解析方向 (Obsidian → Database):
- parse_episode_from_markdown(): 解析 Markdown 并检测翻译修改
- parse_and_backfill_from_markdown(): 回填用户编辑到数据库
"""
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import Episode, AudioSegment, TranscriptCue, Translation, Chapter, MarketingPost
from app.enums.translation_status import TranslationStatus
from app.config import OBSIDIAN_VAULT_PATH, OBSIDIAN_NOTES_SUBDIR, OBSIDIAN_MARKETING_SUBDIR

logger = logging.getLogger(__name__)


@dataclass
class DiffResult:
    """翻译差异结果"""
    cue_id: int
    original: str
    edited: str
    is_edited: bool


class ObsidianService:
    """
    Obsidian 文档生成和解析服务

    负责：
    1. 从数据库生成 Obsidian Markdown 文档
    2. 解析 Obsidian 文档并回填用户编辑
    3. 双向同步：Database ↔ Obsidian

    Attributes:
        db: 数据库会话
        vault_path: Obsidian Vault 路径
    """

    def __init__(self, db: Session, vault_path: Optional[str] = None):
        """
        初始化服务

        Args:
            db: 数据库会话
            vault_path: Obsidian Vault 路径 (默认使用配置)
        """
        self.db = db
        self.vault_path = vault_path or OBSIDIAN_VAULT_PATH

    # ========================================================================
    # 渲染方法 (Database → Markdown)
    # ========================================================================

    def render_episode(self, episode_id: int, language_code: str = "zh") -> str:
        """
        渲染 Episode 为 Obsidian Markdown

        Args:
            episode_id: Episode ID
            language_code: 翻译语言代码

        Returns:
            str: Markdown 内容

        Raises:
            ValueError: Episode 不存在
        """
        logger.debug(f"渲染 Episode: id={episode_id}, language={language_code}")

        # 获取 Episode
        episode = self.db.query(Episode).filter(Episode.id == episode_id).first()
        if not episode:
            raise ValueError(f"Episode not found: id={episode_id}")

        # 获取 Chapters（按时间排序）
        chapters = self.db.query(Chapter).filter(
            Chapter.episode_id == episode_id
        ).order_by(Chapter.start_time).all()

        # 生成 YAML Frontmatter
        frontmatter = self._render_frontmatter(episode)

        # 生成标题和概览
        header = self._render_header(episode)

        # 生成章节导航
        navigation = self._render_chapter_navigation(chapters, episode)

        # 生成章节内容
        content = self._render_chapters_content(chapters, episode, language_code)

        # 如果没有章节，生成所有 Cue 的表格
        if not chapters:
            content = self._render_all_cues_content(episode_id, language_code)

        # 拼接 Markdown，处理 header 为空的情况
        parts = [frontmatter]
        if header:
            parts.append(header)
        parts.extend([navigation, "---", content])
        markdown = "\n\n".join(parts)

        return markdown

    def save_episode(self, episode_id: int, language_code: str = "zh") -> Path:
        """
        生成并保存 Obsidian 文档到 Vault

        Args:
            episode_id: Episode ID
            language_code: 翻译语言代码

        Returns:
            Path: 保存的文件路径
        """
        logger.info(f"保存 Obsidian 文档: episode_id={episode_id}")

        # 渲染 Markdown
        markdown = self.render_episode(episode_id, language_code)

        # 获取 Episode
        episode = self.db.query(Episode).filter(Episode.id == episode_id).first()

        # 生成安全的文件名（使用 display_title）
        safe_title = self._sanitize_filename(episode.display_title)
        filename = f"{episode.id}-{safe_title}.md"

        # 确定保存路径
        notes_dir = Path(self.vault_path) / OBSIDIAN_NOTES_SUBDIR
        notes_dir.mkdir(parents=True, exist_ok=True)

        file_path = notes_dir / filename

        # 写入文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(markdown)

        logger.info(f"Obsidian 文档已保存: {file_path}")
        return file_path

    def _get_episode_path(self, episode_id: int) -> Path:
        """
        获取 Episode 的 Obsidian 文档路径

        Args:
            episode_id: Episode ID

        Returns:
            Path: Obsidian 文档路径
        """
        episode = self.db.query(Episode).filter(Episode.id == episode_id).first()
        if not episode:
            raise ValueError(f"Episode not found: id={episode_id}")

        safe_title = self._sanitize_filename(episode.display_title)
        filename = f"{episode.id}-{safe_title}.md"
        notes_dir = Path(self.vault_path) / OBSIDIAN_NOTES_SUBDIR
        return notes_dir / filename

    def render_marketing_posts(self, episode_id: int) -> str:
        """
        渲染营销文案为 Obsidian Markdown

        Args:
            episode_id: Episode ID

        Returns:
            str: Markdown 内容

        Raises:
            ValueError: Episode 不存在
        """
        logger.debug(f"渲染营销文案: episode_id={episode_id}")

        # 获取 Episode
        episode = self.db.query(Episode).filter(Episode.id == episode_id).first()
        if not episode:
            raise ValueError(f"Episode not found: id={episode_id}")

        # 获取所有营销文案，按角度标签分组
        posts = self.db.query(MarketingPost).filter(
            MarketingPost.episode_id == episode_id
        ).order_by(MarketingPost.created_at).all()

        if not posts:
            return ""

        # 生成 YAML Frontmatter
        frontmatter = self._render_marketing_frontmatter(episode)

        # 生成标题（使用 display_title）
        header = f"# 营销文案 - {episode.display_title}\n\n"

        # 生成内容（按角度分组）
        content = self._render_marketing_content(posts, episode)

        markdown = (
            f"{frontmatter}\n\n"
            f"{header}\n\n"
            f"{content}"
        )

        return markdown

    def save_marketing_posts(self, episode_id: int) -> Path:
        """
        生成并保存营销文案到 Obsidian Vault（单独文件）

        Args:
            episode_id: Episode ID

        Returns:
            Path: 保存的文件路径
        """
        logger.info(f"保存营销文案: episode_id={episode_id}")

        # 渲染 Markdown
        markdown = self.render_marketing_posts(episode_id)

        if not markdown:
            logger.warning(f"没有营销文案可保存: episode_id={episode_id}")
            # 返回 None 或空路径
            return None

        # 获取 Episode
        episode = self.db.query(Episode).filter(Episode.id == episode_id).first()

        # 生成安全的文件名（使用 display_title）
        safe_title = self._sanitize_filename(episode.display_title)
        filename = f"{episode.id}-marketing-{safe_title}.md"

        # 确定保存路径（使用单独的 marketing 目录）
        marketing_dir = Path(self.vault_path) / OBSIDIAN_MARKETING_SUBDIR
        marketing_dir.mkdir(parents=True, exist_ok=True)

        file_path = marketing_dir / filename

        # 写入文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(markdown)

        logger.info(f"营销文案已保存: {file_path}")
        return file_path

    # ========================================================================
    # 解析方法 (Markdown → Database)
    # ========================================================================

    def parse_episode_from_markdown(
        self,
        episode_id: int,
        markdown: str,
        language_code: str = "zh"
    ) -> List[DiffResult]:
        """
        解析 Obsidian 文档，检测翻译修改

        格式解析：
        ### [00:00](cue://1454)
        **Speaker**: Speaker名称
        **英文**: English text...
        **中文**: 中文翻译...

        Args:
            episode_id: Episode ID
            markdown: Markdown 内容
            language_code: 翻译语言代码

        Returns:
            List[DiffResult]: 差异列表
        """
        logger.debug(f"解析 Markdown: episode_id={episode_id}, language={language_code}")

        diffs = []
        lines = markdown.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i]
            line_stripped = line.strip()

            # 查找 Cue 区块的开始（包含 cue:// 的行）
            if "cue://" in line:
                cue_id = self._extract_cue_id_from_anchor(line)
                if cue_id is None:
                    i += 1
                    continue

                # 查找中文翻译行（接下来的几行）
                # 格式: [时间](cue://ID) English text 后面跟空行，然后是中文翻译
                translation_text = None
                j = i + 1
                while j < len(lines) and j < i + 5:  # 最多往后看 5 行
                    current_line = lines[j].strip()
                    # 跳过空行
                    if not current_line:
                        j += 1
                        continue
                    # 如果下一行是 cue:// 开头或 **SPEAKER** 开头，说明没有翻译
                    if "cue://" in current_line or current_line.startswith("**"):
                        break
                    # 否则当前行就是中文翻译
                    translation_text = current_line
                    break
                j += 1

                if translation_text is not None:
                    # 获取数据库中的原始翻译并比较
                    translation = self.db.query(Translation).filter(
                        Translation.cue_id == cue_id,
                        Translation.language_code == language_code
                    ).first()

                    if translation and translation.translation != translation_text:
                        diffs.append(DiffResult(
                            cue_id=cue_id,
                            original=translation.translation,
                            edited=translation_text,
                            is_edited=True
                        ))

            i += 1

        logger.info(f"检测到 {len(diffs)} 个翻译修改")
        return diffs

    def _process_translation_diff(self, cue_id: int, new_translation: str | None, diffs: List[DiffResult]):
        """处理单个翻译的差异检测"""
        if new_translation is None:
            return

        # 获取数据库中的原始翻译
        translation = self.db.query(Translation).filter(
            Translation.cue_id == cue_id,
            Translation.language_code == "zh"
        ).first()

        if not translation:
            logger.warning(f"Translation not found: cue_id={cue_id}")
            return

        # 比较差异
        if translation.translation != new_translation:
            diffs.append(DiffResult(
                cue_id=cue_id,
                original=translation.translation,
                edited=new_translation,
                is_edited=True
            ))

    def parse_and_backfill_from_markdown(
        self,
        episode_id: int,
        markdown: str,
        language_code: str = "zh"
    ) -> int:
        """
        解析并回填翻译修改到数据库

        Args:
            episode_id: Episode ID
            markdown: Markdown 内容
            language_code: 翻译语言代码

        Returns:
            int: 修改的翻译数量
        """
        logger.info(f"回填翻译修改: episode_id={episode_id}")

        # 解析差异
        diffs = self.parse_episode_from_markdown(episode_id, markdown, language_code)

        if not diffs:
            return 0

        # 回填到数据库
        count = 0
        for diff in diffs:
            translation = self.db.query(Translation).filter(
                Translation.cue_id == diff.cue_id,
                Translation.language_code == language_code
            ).first()

            if translation:
                translation.translation = diff.edited
                translation.is_edited = True
                count += 1

        self.db.flush()
        logger.info(f"已回填 {count} 个翻译修改")
        return count

    # ========================================================================
    # 私有辅助方法 - 渲染
    # ========================================================================

    def _render_marketing_frontmatter(self, episode: Episode) -> str:
        """生成营销文案的 YAML Frontmatter"""
        return (
            "---\n"
            f"task_id: {episode.id}\n"
            f"type: marketing\n"
            f"url: {episode.source_url or 'N/A'}\n"
            "status: pending_review\n"
            "---"
        )

    def _render_marketing_content(self, posts: List[MarketingPost], episode: Episode) -> str:
        """生成营销文案内容（按角度分组，使用 display_title）"""
        # 按角度标签分组
        from collections import defaultdict
        posts_by_angle = defaultdict(list)
        for post in posts:
            key = post.chapter_id if post.chapter_id else f"ep_{episode.id}"
            posts_by_angle[(post.angle_tag, key)].append(post)

        sections = []

        # 按角度生成内容
        for (angle, _), angle_posts in sorted(posts_by_angle.items()):
            # 角度标题
            angle_emoji = self._get_angle_emoji(angle)
            section_title = f"## {angle_emoji} {angle}\n\n"

            # 每个角度下可能有多个文案变体
            posts_content = []
            for i, post in enumerate(angle_posts, 1):
                # 章节标识（使用 display_title）
                chapter_info = ""
                if post.chapter_id:
                    chapter = self.db.query(Chapter).filter(Chapter.id == post.chapter_id).first()
                    if chapter:
                        chapter_display_title = chapter.display_title(episode)
                        chapter_info = f"\n\n> **章节**: {chapter_display_title} ({chapter.start_time:.0f}s - {chapter.end_time:.0f}s)\n"

                # 文案编号
                post_header = f"### 文案 {i}\n\n" if len(angle_posts) > 1 else ""

                # 文案内容
                content = f"{post_header}{chapter_info}{post.content}"

                # 元数据
                metadata = f"\n\n---\n\n**元数据**:\n"
                metadata += f"- 创建时间: {post.created_at.strftime('%Y-%m-%d %H:%M')}\n"
                # 计算字数
                word_count = len(post.content)
                metadata += f"- 字数: {word_count}\n"

                posts_content.append(content + metadata)

            sections.append(section_title + "\n\n".join(posts_content))

        return "\n\n".join(sections)

    @staticmethod
    def _get_angle_emoji(angle: str) -> str:
        """根据角度标签返回对应的 emoji"""
        emoji_map = {
            "职场焦虑向": "😰",
            "干货硬核向": "📚",
            "教育学习向": "🎓",
            "情感共鸣向": "❤️",
            "幽默搞笑向": "😄",
            "励志激励向": "💪",
            "案例分析向": "🔍",
            "经验分享向": "💡",
        }
        return emoji_map.get(angle, "📝")

    # ========================================================================
    # 私有辅助方法 - 渲染（原有方法）
    # ========================================================================

    def _render_frontmatter(self, episode: Episode) -> str:
        """生成 YAML Frontmatter"""
        return (
            "---\n"
            f"task_id: {episode.id}\n"
            f"url: {episode.source_url or 'N/A'}\n"
            "status: pending_review\n"
            "---"
        )

    def _render_header(self, episode: Episode) -> str:
        """生成概览（已废弃，返回空字符串）"""
        return ""

    def _render_chapter_navigation(self, chapters: List[Chapter], episode: Episode) -> str:
        """生成章节导航表格（使用 display_title）"""
        if not chapters:
            return ""

        rows = []
        for chapter in chapters:
            # 使用 display_title
            chapter_display_title = chapter.display_title(episode)
            safe_title = self._sanitize_anchor(chapter_display_title)
            time_range = f"{chapter.start_time:.0f} - {chapter.end_time:.0f}"
            # 显示完整的 summary，不截断
            summary = chapter.summary or ""

            rows.append(
                f"| [{chapter.chapter_index + 1}: {chapter_display_title}](#{chapter.chapter_index + 1}-{safe_title}) "
                f"| {time_range} | {summary} |"
            )

        return (
            "## 📑 章节导航\n\n"
            "| 章节 | 时间 | 核心要点 |\n"
            "| :--- | :--- | :--- |\n"
            + "\n".join(rows)
        )

    def _render_chapters_content(self, chapters: List[Chapter], episode: Episode, language_code: str) -> str:
        """生成章节内容（使用 display_title）"""
        sections = []

        for chapter in chapters:
            # 使用 display_title（不包含序号前缀）
            chapter_display_title = chapter.display_title(episode)
            safe_title = self._sanitize_anchor(chapter_display_title)
            section_title = f"## {chapter_display_title}\n\n"

            # 章节摘要
            section_summary = ""
            if chapter.summary:
                section_summary = f"> **章节摘要：** {chapter.summary}\n\n"

            # 章节字幕表格
            # 获取该章节的所有 TranscriptCue
            cues = self.db.query(TranscriptCue).filter(
                TranscriptCue.chapter_id == chapter.id
            ).order_by(TranscriptCue.start_time).all()

            section_table = self._render_bilingual_table(cues, language_code)

            sections.append(section_title + section_summary + section_table)

            # 章节分隔符
            sections.append("\n---\n")

        return "\n".join(sections)

    def _render_all_cues_content(self, episode_id: int, language_code: str) -> str:
        """生成所有 Cue 的表格（无章节时）"""
        # 获取所有 TranscriptCue
        cues = self.db.query(TranscriptCue).join(
            AudioSegment, TranscriptCue.segment_id == AudioSegment.id
        ).filter(
            AudioSegment.episode_id == episode_id
        ).order_by(TranscriptCue.start_time).all()

        return "## 字幕内容\n\n" + self._render_bilingual_table(cues, language_code)

    def _render_bilingual_table(self, cues: List[TranscriptCue], language_code: str) -> str:
        """
        生成双语字幕区块（按说话人分组）

        格式：
        SPEAKER_01

        [00:00](cue://1454) Welcome to The Tim Ferriss Show, I'm your host Tim Ferriss.

        你好，欢迎来到XXXXX

        [00:05](cue://1455) Today we're going to talk about how to learn anything faster.

        今天我们要讨论的是怎么学习得更快

        SPEAKER_00

        [00:12](cue://1456) Hello，everyone！

        大家好！
        """
        if not cues:
            return "暂无字幕内容"

        lines = []
        current_speaker = None

        for i, cue in enumerate(cues):
            translation = cue.get_translation(language_code)
            translation_text = translation if translation else "[未翻译]"

            # 说话人切换时
            if cue.speaker != current_speaker:
                # 如果不是第一个说话人，先空一行分隔
                if current_speaker is not None:
                    lines.append("")  # speaker切换时额外空一行

                # 添加说话人名称（加粗）
                lines.append(f"**{cue.speaker}**")
                lines.append("")  # speaker后空一行
                current_speaker = cue.speaker
            else:
                # 同一个speaker，在英文前空一行（非第一个字幕）
                if i > 0:
                    lines.append("")

            # 添加英文字幕行（锚点 + 英文）
            lines.append(f"{cue.obsidian_anchor} {cue.text}")
            # 英文后空一行（中英分隔）
            lines.append("")
            # 添加中文翻译
            lines.append(translation_text)

        return "\n".join(lines)

    # ========================================================================
    # 私有辅助方法 - 解析
    # ========================================================================

    @staticmethod
    def _extract_cue_id_from_anchor(anchor: str) -> Optional[int]:
        """
        从 Obsidian 锚点中提取 Cue ID

        Args:
            anchor: 锚点字符串，如 "[01:05](cue://1024)" 或 "### [01:05](cue://1024)"

        Returns:
            Optional[int]: Cue ID 或 None
        """
        match = re.search(r'cue://(\d+)', anchor)
        if match:
            return int(match.group(1))
        return None

    # ========================================================================
    # 私有辅助方法 - 工具
    # ========================================================================

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """
        清理文件名（移除特殊字符）

        Args:
            filename: 原始文件名

        Returns:
            str: 安全的文件名
        """
        # 移除或替换特殊字符 (添加更多特殊字符包括 !)
        filename = re.sub(r'[<>:"/\\|?*!\'@#$%^&\[\]{}()+=,;]', '', filename)
        filename = re.sub(r'\s+', '-', filename)
        # 移除开头和结尾的连字符
        filename = filename.strip('-')
        # 限制长度
        if len(filename) > 100:
            filename = filename[:100]
        return filename.lower()

    @staticmethod
    def _sanitize_anchor(anchor: str) -> str:
        """
        清理锚点文本（用于 Markdown 链接）

        Args:
            anchor: 原始文本

        Returns:
            str: 安全的锚点文本
        """
        # 转小写，空格替换为连字符
        anchor = anchor.lower()
        anchor = re.sub(r'[^\w\s-]', '', anchor)
        anchor = re.sub(r'\s+', '-', anchor)
        return anchor
