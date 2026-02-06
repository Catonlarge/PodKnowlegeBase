"""
Segmentation Service - 语义章节切分服务

使用 AI 分析 Transcript 进行语义章节切分，生成中文标题和摘要。
"""
import json
import logging
from datetime import datetime
from typing import List, Dict

from sqlalchemy.orm import Session

from app.models import Episode, Chapter, TranscriptCue
from app.enums.workflow_status import WorkflowStatus

logger = logging.getLogger(__name__)


# Prompt 模板
SEGMENTATION_PROMPT = """
你是一个专业的音频内容分析师。请分析以下英文转录文本，进行**自适应语义章节划分**。

**输入：**
- 英文 Transcript 采样（含时间戳，均匀分布）
- 总时长：{duration} 分钟（{duration_seconds} 秒）
- 采样说明：以下是从完整内容中均匀采样的代表性片段

**核心原则（强制执行）：**
1. **拒绝机械式切分**：章节划分必须依据内容的语义结构，而非时间区间
2. **保持语义完整**：每个章节应该是一个完整的语义单元，避免把一个完整话题切碎
3. **章节数量上限（严格执行）**：
   - **短内容（< 8分钟）**：最多 **2 个章节**
   - **中等内容（8-20分钟）**：最多 **4 个章节**
   - **长内容（> 20分钟）**：最多 **6 个章节**
4. **宁少勿多**：如果内容是一个连贯的对话，**可以不划分**（保留为单一章节）

**任务：**
1. 分析采样内容的语义转折点和话题变化
2. **根据采样内容推断完整内容的章节划分**
3. 章节的 start_time 和 end_time **必须使用秒作为单位**，基于总秒数（{duration_seconds}秒）进行合理分配
4. 直接输出**中文**的章节标题和摘要

**切分决策示例：**
- ❌ 错误：75分钟内容只划分前面2分钟 → 时间范围错误
- ✅ 正确：75分钟内容（4500秒）划分成覆盖完整时长的章节 → 符合实际时长
- ❌ 错误：5分钟内容切分成3个以上章节 → 违反"最多2章"规则
- ✅ 正确：5分钟内容切分成1-2个章节 → 符合规则

**当前内容判定：**
- 总时长：{duration} 分钟（{duration_seconds} 秒）
- 最大章节数：{max_chapters} 个
- **重要**：输出的章节时间范围必须覆盖 [0, {duration_seconds}秒] 的完整区间

**输出格式（JSON）：**
```json
{{
  "chapters": [
    {{
      "title": "开场介绍",
      "summary": "主持人介绍了今天的主题...",
      "start_time": 0.0,
      "end_time": 720.5
    }}
  ]
}}
```
**注意：start_time 和 end_time 必须是秒数**，例如：75分钟的内容应输出 0-4500 秒的范围。

**Transcript (采样):**
{transcript}
"""


class SegmentationService:
    """
    语义章节切分服务

    负责：
    1. 调用 AI 分析 Transcript
    2. 生成 Chapter 记录（中文标题和摘要）
    3. 关联 TranscriptCue 到 Chapter
    4. 更新 Episode.workflow_status
    """

    def __init__(self, db: Session, ai_service):
        """
        初始化章节切分服务

        Args:
            db: 数据库会话
            ai_service: AI 服务实例
        """
        self.db = db
        self.ai_service = ai_service

    def analyze_and_segment(
        self,
        episode_id: int,
        min_chapters: int = 1,
        max_chapters: int = 15
    ) -> List[Chapter]:
        """
        分析并切分章节

        Args:
            episode_id: Episode ID
            min_chapters: 最小章节数
            max_chapters: 最大章节数

        Returns:
            List[Chapter]: 生成的章节列表

        Raises:
            ValueError: Episode 不存在或未转录
        """
        # 验证 Episode 存在且已转录（或已校对）
        episode = self.db.query(Episode).filter(Episode.id == episode_id).first()
        if not episode:
            raise ValueError(f"Episode 不存在: episode_id={episode_id}")

        # 允许 TRANSCRIBED 或 PROOFREAD 状态
        valid_statuses = [
            WorkflowStatus.TRANSCRIBED.value,
            WorkflowStatus.PROOFREAD.value
        ]
        if episode.workflow_status not in valid_statuses:
            raise ValueError(
                f"Episode 未转录，当前状态: {WorkflowStatus(episode.workflow_status).label}"
            )

        # 获取所有 TranscriptCue（按时间排序）
        cues = (
            self.db.query(TranscriptCue)
            .join(AudioSegment, AudioSegment.id == TranscriptCue.segment_id)
            .filter(AudioSegment.episode_id == episode_id)
            .order_by(TranscriptCue.start_time)
            .all()
        )

        if not cues:
            raise ValueError(f"Episode 没有转录内容: episode_id={episode_id}")

        # 构建 Transcript 文本
        transcript_text = self._build_transcript_text(cues)

        # 调用 AI 分析
        duration_minutes = episode.duration / 60

        # 计算最大章节数（根据PRD要求）
        if duration_minutes < 8:
            max_chapters = 2
        elif duration_minutes < 20:
            max_chapters = 4
        else:
            max_chapters = 6

        prompt = SEGMENTATION_PROMPT.format(
            duration=f"{duration_minutes:.1f}",
            duration_seconds=f"{episode.duration:.0f}",
            max_chapters=max_chapters,
            transcript=transcript_text
        )

        logger.info(f"开始章节切分: episode_id={episode_id}, cues数量={len(cues)}")

        # 直接调用 OpenAI 兼容 API（绕过 AIService 的 word/phrase/sentence 解析）
        response_text = self._call_ai_for_segmentation(prompt)

        # 解析 AI 响应
        chapters_data = self._parse_ai_response(response_text)

        # 创建 Chapter 记录
        chapters = self._create_chapters(episode_id, chapters_data)

        # 关联 TranscriptCue 到 Chapter
        self._associate_cues_to_chapters(episode_id, chapters)

        # 更新 Episode 状态
        self._update_episode_status(episode_id)

        logger.info(f"章节切分完成: episode_id={episode_id}, 章节数={len(chapters)}")

        return chapters

    def _build_transcript_text(
        self,
        cues: List[TranscriptCue],
        max_cues: int = 150
    ) -> str:
        """
        构建 Transcript 文本（含时间戳）

        对于长内容，使用**基于时间的均匀采样策略**：
        - 确保采样的内容覆盖完整的时间范围
        - 从开头到结尾均匀分布采样点

        Args:
            cues: TranscriptCue 列表
            max_cues: 最大处理的 cue 数量（默认150）

        Returns:
            str: 格式化的 Transcript 文本
        """
        if len(cues) <= max_cues:
            # 短内容：全部处理
            sampled_cues = cues
        else:
            # 长内容：基于时间均匀采样
            # 计算总时长
            total_duration = cues[-1].start_time
            # 计算目标采样间隔（秒）
            sample_interval = total_duration / max_cues

            sampled_cues = []
            last_sampled_time = -1

            for cue in cues:
                # 每隔 sample_interval 采样一条
                if cue.start_time - last_sampled_time >= sample_interval:
                    sampled_cues.append(cue)
                    last_sampled_time = cue.start_time

                    if len(sampled_cues) >= max_cues:
                        break

            # 确保最后一条被包含
            if sampled_cues and sampled_cues[-1].id != cues[-1].id:
                sampled_cues.append(cues[-1])

            logger.info(f"基于时间均匀采样: 原始 {len(cues)} 条 -> 采样后 {len(sampled_cues)} 条")
            logger.info(f"时间覆盖: {sampled_cues[0].start_time:.0f}s - {sampled_cues[-1].start_time:.0f}s")

        # 构建文本
        lines = []
        for cue in sampled_cues:
            minutes = int(cue.start_time // 60)
            seconds = int(cue.start_time % 60)
            time_str = f"[{minutes:02d}:{seconds:02d}]"
            lines.append(f"{time_str} {cue.speaker}: {cue.text}")
        return "\n".join(lines)

    def _parse_ai_response(
        self,
        response_text: str
    ) -> List[Dict]:
        """
        解析 AI 返回的 JSON 响应

        Args:
            response_text: AI 返回的 JSON 字符串

        Returns:
            List[Dict]: 章节数据列表

        Raises:
            ValueError: JSON 解析失败或格式错误
        """
        # 去除可能的 markdown 代码块标记
        text = response_text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 解析失败: {e}") from e

        if "chapters" not in data:
            raise ValueError("AI 响应缺少 'chapters' 字段")

        chapters = data["chapters"]
        if not isinstance(chapters, list):
            raise ValueError("'chapters' 应该是列表类型")

        return chapters

    def _create_chapters(
        self,
        episode_id: int,
        chapters_data: List[Dict]
    ) -> List[Chapter]:
        """
        创建 Chapter 记录

        Args:
            episode_id: Episode ID
            chapters_data: 章节数据列表

        Returns:
            List[Chapter]: 创建的 Chapter 列表
        """
        chapters = []
        for index, chapter_data in enumerate(chapters_data):
            chapter = Chapter(
                episode_id=episode_id,
                chapter_index=index,
                title=chapter_data.get("title", f"章节{index + 1}"),
                summary=chapter_data.get("summary"),
                start_time=float(chapter_data.get("start_time", 0)),
                end_time=float(chapter_data.get("end_time", 0)),
                status="completed",
                ai_model_used=str(getattr(self.ai_service, "provider", "unknown")),
                processed_at=datetime.now()
            )
            self.db.add(chapter)
            chapters.append(chapter)

        self.db.flush()
        return chapters

    def _associate_cues_to_chapters(
        self,
        episode_id: int,
        chapters: List[Chapter]
    ) -> None:
        """
        关联 TranscriptCue 到 Chapter

        根据 cue.start_time 判断属于哪个章节：
        chapter.start_time <= cue.start_time < chapter.end_time

        Args:
            episode_id: Episode ID
            chapters: Chapter 列表
        """
        # 获取该 Episode 的所有 Cue
        cues = (
            self.db.query(TranscriptCue)
            .join(AudioSegment, AudioSegment.id == TranscriptCue.segment_id)
            .filter(AudioSegment.episode_id == episode_id)
            .all()
        )

        for cue in cues:
            # 找到对应的章节
            for chapter in chapters:
                if chapter.start_time <= cue.start_time < chapter.end_time:
                    cue.chapter_id = chapter.id
                    break
            # 边界情况：最后一个时间点的 cue
            if cue.start_time == chapters[-1].end_time:
                cue.chapter_id = chapters[-1].id

        self.db.flush()

    def _call_ai_for_segmentation(self, prompt: str) -> str:
        """
        直接调用 AI API 进行章节切分（返回原始文本）

        Args:
            prompt: 提示词

        Returns:
            str: AI 返回的原始文本

        Raises:
            RuntimeError: AI 调用失败
        """
        from openai import OpenAI
        from app.config import MOONSHOT_API_KEY, MOONSHOT_BASE_URL, MOONSHOT_MODEL, AI_QUERY_TIMEOUT

        if not MOONSHOT_API_KEY:
            raise ValueError("MOONSHOT_API_KEY 未设置")

        try:
            client = OpenAI(
                api_key=MOONSHOT_API_KEY,
                base_url=MOONSHOT_BASE_URL
            )

            logger.info(f"调用 Moonshot API 进行章节切分 (model={MOONSHOT_MODEL})")

            completion = client.chat.completions.create(
                model=MOONSHOT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的音频内容分析师。你擅长识别内容的语义结构，拒绝机械式时间切分，始终保持章节的语义完整性。对于短内容，你会减少切分；对于长内容，你会适当增加切分点，但绝不碎片化。"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.6,  # kimi-k2-turbo-preview supports 0-1 (default 0.6)
            )

            response_text = completion.choices[0].message.content
            logger.info(f"AI 响应长度: {len(response_text)} 字符")
            return response_text

        except Exception as e:
            logger.error(f"AI 调用失败: {e}")
            raise RuntimeError(f"章节切分 AI 调用失败: {e}") from e

    def _update_episode_status(self, episode_id: int) -> None:
        """
        更新 Episode.workflow_status 为 SEGMENTED

        Args:
            episode_id: Episode ID
        """
        episode = self.db.query(Episode).filter(Episode.id == episode_id).first()
        if episode:
            episode.workflow_status = WorkflowStatus.SEGMENTED.value
            self.db.flush()


# 导入 AudioSegment（避免循环导入）
from app.models import AudioSegment
