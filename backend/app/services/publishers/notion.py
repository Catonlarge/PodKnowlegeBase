"""
Notion Publisher - Notion 平台发布服务

负责将 Episode 和 MarketingPost 内容发布到 Notion 工作区：
1. validate_config() - 验证 Notion API 配置
2. publish_episode() - 发布 Episode 到 Notion
3. publish_marketing_posts() - 发布营销文案到 Notion
4. create_episode_page() - 创建 Notion 页面
5. render_chapters_block() - 渲染章节表格块
6. render_transcripts_table() - 渲染字幕表格块

依赖：pip install notion-client
"""
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from sqlalchemy.orm import Session

from app.models import Episode, Chapter, TranscriptCue, MarketingPost, PublicationRecord
from app.config import NOTION_API_KEY, NOTION_PARENT_PAGE_ID, NOTION_API_VERSION

try:
    from notion_client import Client
except ImportError:
    Client = None
    logging.warning("notion-client 未安装，请运行: pip install notion-client")

logger = logging.getLogger(__name__)


class NotionPublisher:
    """
    Notion 平台发布服务

    负责：
    1. 将 Episode 内容发布为 Notion 页面
    2. 将营销文案发布到 Notion 数据库
    3. 生成 Notion Block 格式的内容

    Attributes:
        client: Notion API 客户端
        parent_page_id: 父页面 ID（用于创建子页面）
    """

    def __init__(self, db: Optional[Session] = None):
        """
        初始化 NotionPublisher

        Args:
            db: 数据库会话（用于保存 PublicationRecord）

        Raises:
            ValueError: NOTION_API_KEY 未配置
            ImportError: notion-client 未安装
        """
        if not Client:
            raise ImportError("notion-client 未安装，请运行: pip install notion-client")

        if not NOTION_API_KEY:
            raise ValueError("NOTION_API_KEY 未配置")

        self.client = Client(auth=NOTION_API_KEY, notion_version=NOTION_API_VERSION)
        self.parent_page_id = NOTION_PARENT_PAGE_ID
        self.db = db

    # ========================================================================
    # 配置验证
    # ========================================================================

    def validate_config(self) -> bool:
        """
        验证 Notion API 配置是否有效

        Returns:
            bool: 配置有效返回 True，否则返回 False
        """
        if not NOTION_API_KEY:
            logger.warning("NOTION_API_KEY 未配置")
            return False

        try:
            # 使用 search API 测试连接
            response = self.client.search(
                filter={
                    "value": "page",
                    "property": "object"
                }
            )
            logger.info("Notion API 连接成功")
            return True
        except Exception as e:
            logger.error(f"Notion API 连接失败: {e}")
            return False

    # ========================================================================
    # Episode 发布
    # ========================================================================

    def publish_episode(self, episode: Episode) -> PublicationRecord:
        """
        发布 Episode 到 Notion

        页面结构：
        1. 概览（callout）
        2. 章节总结（无链接，快速浏览）
        3. 字幕内容
           - 章节标题
           - 字幕（左右两列布局）
        4. 章节导航（含跳转链接）

        Args:
            episode: Episode 对象

        Returns:
            PublicationRecord: 发布记录
        """
        logger.info(f"发布 Episode 到 Notion: id={episode.id}, title={episode.title}")

        try:
            # 创建 Notion 页面
            page_id = self.create_episode_page(
                title=episode.title,
                parent_page_id=self.parent_page_id
            )

            # 获取章节列表
            chapters = self.db.query(Chapter).filter(
                Chapter.episode_id == episode.id
            ).order_by(Chapter.start_time).all()

            # 存储章节标题 block ID（用于创建跳转链接）
            chapter_block_ids = {}

            # 准备初始内容块（概览 + 章节总结 + 字幕内容）
            blocks = []

            # 1. 添加概览
            if episode.ai_summary:
                blocks.append(self._render_callout_block(episode.ai_summary))

            # 2. 添加章节总结（无链接，用于快速浏览）
            if chapters:
                blocks.extend(self.render_chapters_block(chapters))

            # 3. 添加"字幕内容"标题
            blocks.append(self._render_heading_block("字幕内容", level=2))

            # 4. 按章节添加标题和字幕内容
            for chapter in chapters:
                # 章节标题
                heading_block = self._render_heading_block(
                    f"{chapter.chapter_index + 1}: {chapter.title}",
                    level=3
                )
                blocks.append(heading_block)

                # 获取字幕并渲染
                cues = self.db.query(TranscriptCue).filter(
                    TranscriptCue.chapter_id == chapter.id
                ).order_by(TranscriptCue.start_time).all()

                transcript_blocks = self.render_transcripts_table(cues, language_code="zh")
                if transcript_blocks:
                    blocks.extend(transcript_blocks)

            # 批量添加初始内容块
            for i in range(0, len(blocks), 100):
                batch = blocks[i:i + 100]
                response = self.client.blocks.children.append(block_id=page_id, children=batch)
                # 保存章节标题的 block ID
                for result in response.get("results", []):
                    block_type = result.get("type", "")
                    if block_type == "heading_3":
                        # 从 heading 内容中提取章节编号
                        heading_text = ""
                        if result.get(block_type, {}).get("rich_text"):
                            for text_obj in result[block_type]["rich_text"]:
                                if text_obj.get("type") == "text":
                                    heading_text = text_obj["text"].get("content", "")
                                    # 解析章节编号（格式："1: Chapter Title"）
                                    if ": " in heading_text:
                                        chapter_num = int(heading_text.split(":")[0].strip())
                                        chapter_block_ids[chapter_num] = result["id"]

            # 5. 添加章节导航（含跳转链接，在页面底部）
            if chapters and chapter_block_ids:
                nav_blocks = []

                # 添加标题
                nav_blocks.append(self._render_heading_block("章节导航（点击跳转）", level=2))

                # 为每个章节创建导航项
                for chapter in chapters:
                    chapter_num = chapter.chapter_index + 1
                    block_id = chapter_block_ids.get(chapter_num)

                    # 截取摘要
                    summary = chapter.summary or ""
                    if len(summary) > 80:
                        summary = summary[:80] + "..."

                    if block_id:
                        # 创建带链接的导航项（使用页面内锚点）
                        nav_blocks.append(self._render_link_block(
                            title=f"{chapter_num}. {chapter.title}",
                            url=self._get_notion_block_url(block_id, page_id),
                            summary=summary
                        ))
                    else:
                        # 降级：无链接的文本
                        item_text = f"**{chapter_num}. {chapter.title}**\n\n{summary}"
                        nav_blocks.append(self._render_paragraph_block(item_text))

                # 添加分隔线
                nav_blocks.append(self._render_divider_block())

                # 在页面末尾添加导航
                for i in range(0, len(nav_blocks), 100):
                    batch = nav_blocks[i:i + 100]
                    self.client.blocks.children.append(block_id=page_id, children=batch)

            # 创建发布记录
            record = PublicationRecord(
                episode_id=episode.id,
                platform="notion",
                platform_record_id=page_id,
                status="success",
                published_at=datetime.utcnow()
            )

            if self.db:
                self.db.add(record)
                self.db.flush()

            logger.info(f"Episode 发布成功: page_id={page_id}")
            return record

        except Exception as e:
            logger.error(f"Episode 发布失败: {e}")
            # 创建失败记录
            record = PublicationRecord(
                episode_id=episode.id,
                platform="notion",
                status="failed",
                error_message=str(e)
            )

            if self.db:
                self.db.add(record)
                self.db.flush()

            return record

    # ========================================================================
    # 营销文案发布
    # ========================================================================

    def publish_marketing_posts(self, posts: List[MarketingPost]) -> List[PublicationRecord]:
        """
        发布营销文案到 Notion

        Args:
            posts: MarketingPost 列表

        Returns:
            List[PublicationRecord]: 发布记录列表
        """
        logger.info(f"发布 {len(posts)} 条营销文案到 Notion")

        records = []
        for post in posts:
            try:
                # 创建页面
                page_id = self.create_episode_page(
                    title=post.title,
                    parent_page_id=self.parent_page_id
                )

                # 添加内容
                # 计算 word_count
                word_count = len(post.content)
                blocks = [
                    self._render_paragraph_block(post.content),
                    self._render_divider_block(),
                    self._render_paragraph_block(
                        f"**平台**: {post.platform}\n"
                        f"**角度**: {post.angle_tag}\n"
                        f"**字数**: {word_count}"
                    )
                ]

                self.client.blocks.children.append(block_id=page_id, children=blocks)

                record = PublicationRecord(
                    episode_id=post.episode_id,
                    platform="notion",
                    platform_record_id=page_id,
                    status="success",
                    published_at=datetime.utcnow()
                )

                if self.db:
                    self.db.add(record)
                    self.db.flush()

                records.append(record)

            except Exception as e:
                logger.error(f"营销文案发布失败: {e}")
                record = PublicationRecord(
                    episode_id=post.episode_id,
                    platform="notion",
                    status="failed",
                    error_message=str(e)
                )

                if self.db:
                    self.db.add(record)
                    self.db.flush()

                records.append(record)

        return records

    # ========================================================================
    # 页面创建
    # ========================================================================

    def create_episode_page(
        self,
        title: str,
        parent_page_id: Optional[str] = None,
        parent_type: str = "page_id"
    ) -> str:
        """
        创建 Notion 页面

        Args:
            title: 页面标题
            parent_page_id: 父节点 ID（默认使用配置中的 parent_page_id）
            parent_type: 父节点类型（"page_id" 或 "database_id"）

        Returns:
            str: 创建的页面 ID
        """
        parent_id = parent_page_id or self.parent_page_id

        # Notion API 要求 parent 结构为：{"type": "page_id", "page_id": "xxx"}
        # 或者 {"type": "database_id", "database_id": "xxx"}
        parent_dict = {
            "type": parent_type,
            parent_type: parent_id
        }

        response = self.client.pages.create(
            parent=parent_dict,
            properties={
                "title": [
                    {
                        "text": {
                            "content": title
                        }
                    }
                ]
            }
        )

        page_id = response["id"]
        logger.info(f"创建 Notion 页面成功: page_id={page_id}, title={title}")

        return page_id

    # ========================================================================
    # Block 渲染方法
    # ========================================================================

    def render_chapters_block(self, chapters: List[Chapter]) -> List[Dict[str, Any]]:
        """
        渲染章节导航块（简化版，无时间戳）

        使用单个 callout 块包含所有章节导航。
        使用 rich_text 数组实现正确的加粗渲染。

        Args:
            chapters: Chapter 列表

        Returns:
            List[Dict]: Notion blocks 结构
        """
        if not chapters:
            return []

        # 构建 rich_text 数组，每个文本片段单独设置样式
        rich_text = []

        # 添加标题 "章节导航"（加粗）
        rich_text.append({
            "type": "text",
            "text": {"content": "章节导航"},
            "annotations": {"bold": True}
        })

        # 添加空行
        rich_text.append({"type": "text", "text": {"content": "\n\n"}})

        # 添加每个章节
        for i, chapter in enumerate(chapters):
            # 截取摘要
            summary = chapter.summary or ""
            if len(summary) > 80:
                summary = summary[:80] + "..."

            # 章节标题（加粗）
            rich_text.append({
                "type": "text",
                "text": {
                    "content": f"{chapter.chapter_index + 1}. {chapter.title}"
                },
                "annotations": {"bold": True}
            })

            # 摘要（普通文本）
            if summary:
                rich_text.append({
                    "type": "text",
                    "text": {"content": f" {summary}"}
                })

            # 章节之间添加空行（除了最后一个章节）
            if i < len(chapters) - 1:
                rich_text.append({"type": "text", "text": {"content": "\n\n"}})

        # 返回蓝色背景的 callout 块
        return [{
            "type": "callout",
            "callout": {
                "rich_text": rich_text,
                "color": "blue_background"
            }
        }]

    def render_transcripts_table(
        self,
        cues: List[TranscriptCue],
        language_code: str = "zh"
    ) -> List[Dict[str, Any]]:
        """
        渲染中英对照字幕（按 speaker 分组）

        格式：
        - Speaker 标题（callout）
        - 该 speaker 的所有字幕（每个 callout 包含时间戳+英文+中文）

        Args:
            cues: TranscriptCue 列表
            language_code: 翻译语言代码

        Returns:
            List[Dict]: Notion block 结构列表
        """
        if not cues:
            return []

        blocks = []

        # 按 speaker 分组
        from collections import defaultdict
        speaker_cues = defaultdict(list)
        for cue in cues:
            # 使用 effective_text（如果已校对，使用校对后的文本）
            speaker_cues[cue.speaker].append(cue)

        # 为每个 speaker 创建内容
        for speaker, speaker_cue_list in speaker_cues.items():
            # Speaker 标题 callout
            speaker_display = self._format_speaker_name(speaker)
            blocks.append({
                "type": "callout",
                "callout": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": speaker_display
                            },
                            "annotations": {
                                "bold": True
                            }
                        }
                    ],
                    "color": "blue_background"
                }
            })

            # 该 speaker 的所有字幕
            for cue in speaker_cue_list:
                # 格式化时间
                minutes = int(cue.start_time // 60)
                seconds = int(cue.start_time % 60)
                time_str = f"{minutes:02d}:{seconds:02d}"

                # 获取翻译
                translation = cue.get_translation(language_code) if hasattr(cue, 'get_translation') else None
                translation_text = translation if translation else ""

                # 使用 effective_text（校对后的文本或原文）
                text_content = cue.effective_text if hasattr(cue, 'effective_text') else cue.text

                # 构建 rich_text 数组，时间戳加粗
                cue_rich_text = [
                    {
                        "type": "text",
                        "text": {"content": time_str},
                        "annotations": {"bold": True}
                    },
                    {
                        "type": "text",
                        "text": {"content": f" {text_content}"}
                    }
                ]

                # 添加翻译
                if translation_text:
                    cue_rich_text.append({
                        "type": "text",
                        "text": {"content": f"\n\n{translation_text}"}
                    })

                # 创建字幕 callout block
                blocks.append({
                    "type": "callout",
                    "callout": {
                        "rich_text": cue_rich_text,
                        "color": "gray_background"
                    }
                })

        return blocks

    @staticmethod
    def _format_speaker_name(speaker: str) -> str:
        """
        格式化 speaker 名称

        将 SPEAKER_00 格式转换为 Speaker1 格式

        Args:
            speaker: 原始 speaker 标识符

        Returns:
            str: 格式化后的 speaker 名称
        """
        # 如果是 SPEAKER_XX 格式，转换为 Speaker1 格式
        if speaker.startswith("SPEAKER_"):
            try:
                num = int(speaker.split("_")[1])
                return f"Speaker{num + 1}："
            except (ValueError, IndexError):
                return f"{speaker}："
        return f"{speaker}："

    # ========================================================================
    # 私有辅助方法 - Block 创建
    # ========================================================================

    @staticmethod
    def _create_text_cell(text: str) -> Dict[str, Any]:
        """创建文本单元格"""
        return {
            "type": "text",
            "text": {
                "content": text
            }
        }

    @staticmethod
    def _render_heading_block(text: str, level: int = 1) -> Dict[str, Any]:
        """渲染标题块"""
        heading_type = f"heading_{level}"
        return {
            "type": heading_type,
            heading_type: {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": text
                        }
                    }
                ]
            }
        }

    @staticmethod
    def _render_paragraph_block(text: str) -> Dict[str, Any]:
        """渲染段落块"""
        return {
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": text
                        }
                    }
                ]
            }
        }

    @staticmethod
    def _render_callout_block(text: str) -> Dict[str, Any]:
        """渲染标注块"""
        return {
            "type": "callout",
            "callout": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": f"全文概览：{text}"
                        }
                    }
                ]
            }
        }

    @staticmethod
    def _render_divider_block() -> Dict[str, Any]:
        """渲染分割线块"""
        return {
            "type": "divider",
            "divider": {}
        }

    @staticmethod
    def _render_empty_paragraph() -> Dict[str, Any]:
        """渲染空段落块（用于添加空行）"""
        return {
            "type": "paragraph",
            "paragraph": {
                "rich_text": []
            }
        }

    @staticmethod
    def _render_link_block(title: str, url: str, summary: str = "") -> Dict[str, Any]:
        """
        渲染带链接的段落块

        Args:
            title: 链接标题
            url: 链接 URL
            summary: 摘要文本（可选）

        Returns:
            Dict: Notion paragraph block 结构
        """
        # 使用 Notion rich text 格式，带链接和加粗
        rich_text = [
            {
                "type": "text",
                "text": {
                    "content": title,
                    "link": {"url": url}
                },
                "annotations": {
                    "bold": True
                }
            }
        ]

        # 添加摘要
        if summary:
            rich_text.append({
                "type": "text",
                "text": {
                    "content": f"\n\n{summary}"
                }
            })

        return {
            "type": "paragraph",
            "paragraph": {
                "rich_text": rich_text
            }
        }

    @staticmethod
    def _get_notion_block_url(block_id: str, page_id: Optional[str] = None) -> str:
        """
        生成 Notion block 的跳转 URL

        使用页面内锚点格式，实现页面内平滑跳转（不重新加载页面）。
        格式：https://www.notion.so/{clean_page_id}#{clean_block_id}

        Args:
            block_id: Notion block ID
            page_id: Notion page ID (required for page-internal anchor)

        Returns:
            str: Notion page internal anchor link

        Examples:
            With page_id: https://www.notion.so/abc123def456ghi789#jkl012mno345
        """
        clean_block_id = block_id.replace("-", "")
        if page_id:
            clean_page_id = page_id.replace("-", "")
            # 使用 www.notion.so 和页面内锚点格式
            return f"https://www.notion.so/{clean_page_id}#{clean_block_id}"
        # 降级：如果没有 page_id，返回 block 直接链接（会打开新页面）
        return f"https://www.notion.so/{clean_block_id}"
