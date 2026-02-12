"""
Segmentation Service - 语义章节切分服务

使用 AI 分析 Transcript 进行语义章节切分，生成中文标题和摘要。

Migrated to use StructuredLLM with Pydantic validation and retry logic.
"""
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple

from sqlalchemy.orm import Session
from langchain_core.messages import SystemMessage, HumanMessage

from app.models import Episode, Chapter, TranscriptCue, AudioSegment
from app.enums.workflow_status import WorkflowStatus
from app.config import (
    MOONSHOT_API_KEY, MOONSHOT_BASE_URL, MOONSHOT_MODEL,
    ZHIPU_API_KEY, ZHIPU_BASE_URL, ZHIPU_MODEL,
    AI_TEMPERATURE_SEGMENTATION
)
from app.services.ai.structured_llm import StructuredLLM
from app.services.ai.schemas.segmentation_schema import SegmentationResponse, Chapter as ChapterSchema
from app.services.ai.validators.segmentation_validator import SegmentationValidator

logger = logging.getLogger(__name__)

# 兜底策略常量（折中：优先完整，仅在 API 失败时重试采样，且采样粒度温和）
FALLBACK_MAX_CUES = 2000  # 采样兜底时 2000 条（75 分钟约 2.25 秒/条，保留更多语义与转折点）

# Prompt 模板 - Chain-of-Thought 两步骤 + Few-shot
SEGMENTATION_PROMPT_FULL = """
你是一个专业的音频内容分析师。请分析以下英文转录文本，进行**自适应语义章节划分**。

**输入：**
- 英文 Transcript（完整内容，含时间戳 [MM:SS]）
- 总时长：{duration} 分钟（{duration_seconds} 秒）

**时间戳格式：** [MM:SS] 表示 分:秒，如 [25:00]=1500秒，[37:30]=2250秒

**核心原则：**
1. 章节划分依据语义转折点，拒绝机械切分
2. 章节数量上限：短内容最多2章，中等最多4章，长内容最多6章
3. 时间范围必须覆盖 [0, {duration_seconds}秒] 完整区间

**Chain-of-Thought 两步骤思路：**

**第一步：查看大概的章节划分，输出时间戳范围**
- 通读 transcript，识别语义转折点（话题切换、主持人换方向等）
- 根据 [MM:SS] 时间戳确定各章节的 start_time、end_time（秒）
- 将推理过程写入 step1_reasoning

**第二步：依据每个范围的内容，输出这章对应的标题**（每章必填 reasoning，包含三子步）
1. **锁定时间范围**：start_time～end_time 对应 transcript 中的 [MM:SS]
2. **归纳该段主题**：列出该时间段讨论的核心话题
3. **推导标题**：根据归纳提炼 15-25 字中文标题，**需包含 1-2 个关键词或具体事件**，避免过于笼统（如单用「开场」「收尾」）

---

**Few-shot 示例：**

假设某播客 transcript 片段如下（总时长 10 分钟）：
```
[00:00] Host: Today we talk about AI talent war. Meta is offering $100M...
[02:30] Guest: At Anthropic we are less affected because people care about mission...
[05:00] Host: OK I want to go in a different direction. Why did you leave OpenAI?
[05:30] Guest: We felt safety wasn't the top priority there. Sam talked about three tribes...
[08:00] Host: Quick fire round. Best book? Guest: Good Strategy Bad Strategy...
```

**期望输出：**
```json
{{
  "step1_reasoning": "第一步：发现转折点位于 [05:00] (Host 明确换方向「go in a different direction」)、[08:00] (进入闪电问答)，故划分 0-300s、300-480s、480-600s 三章",
  "chapters": [
    {{
      "start_time": 0.0,
      "end_time": 300.0,
      "reasoning": "第二步：1) 锁定 0-300s 对应 [00:00]-[05:00]；2) 该段讨论：AI 人才争夺、Meta 挖角、Anthropic 使命留人；3) 故标题「Meta 天价挖角与 Anthropic 使命留人」",
      "title": "Meta 天价挖角与 Anthropic 使命留人",
      "summary": "主持人引出 AI 人才争夺话题，嘉宾解释 Anthropic 因使命驱动受冲击较小"
    }},
    {{
      "start_time": 300.0,
      "end_time": 480.0,
      "reasoning": "第二步：1) 锁定 300-480s 对应 [05:00]-[08:00]；2) 该段讨论：换方向、离开 OpenAI 原因、安全非最高优先级、三部落；3) 故标题「因安全非最高优先级而离开 OpenAI」",
      "title": "因安全非最高优先级而离开 OpenAI",
      "summary": "主持人换方向后，嘉宾详述因安全非最高优先级而离开 OpenAI 的经过"
    }},
    {{
      "start_time": 480.0,
      "end_time": 600.0,
      "reasoning": "第二步：1) 锁定 480-600s 对应 [08:00]-[10:00]；2) 该段讨论：闪电问答、书籍推荐；3) 故标题「闪电问答：书籍推荐与人生信条」",
      "title": "闪电问答：书籍推荐与人生信条",
      "summary": "闪电问答环节，嘉宾推荐书籍"
    }}
  ]
}}
```

---

**请仿照上述格式，对下方 Transcript 进行分析并输出 JSON：**

**Transcript:**
{transcript}
"""

SEGMENTATION_PROMPT_SAMPLED = """
你是一个专业的音频内容分析师。以下是从完整内容均匀采样的 transcript 片段，请推断完整内容的章节划分。

**输入：** 采样 Transcript（含时间戳 [MM:SS]），总时长 {duration} 分钟（{duration_seconds} 秒）

**时间戳格式：** [MM:SS] = 分:秒，如 [25:00]=1500秒

**Chain-of-Thought 两步骤：**
1. **第一步**：查看大概的章节划分，输出时间戳范围；将推理写入 step1_reasoning
2. **第二步**：依据每个范围的内容，输出该章对应的标题；每章 reasoning 需包含：
   - 1) 锁定时间范围：对应 [MM:SS]
   - 2) 归纳该段主题：列出核心话题
   - 3) 推导标题：15-25 字，含 1-2 个关键词或具体事件，避免笼统

**Few-shot 参考（reasoning 格式）：**
某章 reasoning 示例："第二步：1) 锁定 300-480s 对应 [05:00]-[08:00]；2) 该段讨论：换方向、离开 OpenAI、安全非最高优先级；3) 故标题「因安全非最高优先级而离开 OpenAI」"

**输出格式（JSON）：**
```json
{{"step1_reasoning": "第一步：...", "chapters": [{{"start_time": 0.0, "end_time": 750.0, "reasoning": "第二步：1) 锁定... 2) 该段讨论... 3) 故标题「...」", "title": "...", "summary": "..."}}]}}
```

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

    Uses StructuredLLM with Pydantic validation for reliable structured output.
    """

    def __init__(
        self,
        db: Session,
        provider: str = "moonshot",
        api_key: str = None,
        base_url: str = None,
        model: str = None
    ):
        """
        初始化章节切分服务

        Args:
            db: 数据库会话
            provider: AI provider name (moonshot, zhipu, gemini)
            api_key: API key (optional, defaults to config)
            base_url: Base URL (optional, defaults to config)
            model: Model name (optional, defaults to config)
        """
        self.db = db
        self.provider = provider

        # Initialize StructuredLLM
        if api_key is None:
            if provider == "moonshot":
                api_key = MOONSHOT_API_KEY
                base_url = base_url or MOONSHOT_BASE_URL
                model = model or MOONSHOT_MODEL
            elif provider == "zhipu":
                api_key = ZHIPU_API_KEY
                base_url = base_url or ZHIPU_BASE_URL
                model = model or ZHIPU_MODEL
            elif provider == "gemini":
                from app.config import GEMINI_API_KEY, GEMINI_MODEL
                api_key = GEMINI_API_KEY
                model = model or GEMINI_MODEL
            else:
                raise ValueError(f"Unsupported provider: {provider}")

        try:
            self.structured_llm = StructuredLLM(
                provider=provider,
                model=model,
                api_key=api_key,
                base_url=base_url,
                temperature=AI_TEMPERATURE_SEGMENTATION
            )
            logger.info(f"SegmentationService: Initialized {provider} StructuredLLM")
        except Exception as e:
            logger.error(f"Failed to initialize StructuredLLM: {e}")
            self.structured_llm = None

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

        # 构建 Transcript 文本（优先不采样）
        transcript_text, use_sampling = self._build_transcript_text(cues)
        if use_sampling:
            logger.info(f"内容过长，使用采样兜底: {len(cues)} 条 -> 采样后发送")

        duration_minutes = episode.duration / 60
        if duration_minutes < 8:
            max_chapters = 2
        elif duration_minutes < 20:
            max_chapters = 4
        else:
            max_chapters = 6

        prompt_template = SEGMENTATION_PROMPT_SAMPLED if use_sampling else SEGMENTATION_PROMPT_FULL
        prompt = prompt_template.format(
            duration=f"{duration_minutes:.1f}",
            duration_seconds=f"{episode.duration:.0f}",
            max_chapters=max_chapters,
            transcript=transcript_text
        )

        logger.info(f"开始章节切分: episode_id={episode_id}, cues={len(cues)}, 模式={'采样' if use_sampling else '完整'}")

        # 调用 AI（优先完整模式，失败时重试采样模式）
        response = self._call_ai_with_fallback(
            prompt=prompt,
            cues=cues,
            episode=episode,
            use_sampling=use_sampling
        )

        # 创建 Chapter 记录
        chapters = self._create_chapters(episode_id, response)

        # 关联 TranscriptCue 到 Chapter
        self._associate_cues_to_chapters(episode_id, chapters)

        # 更新 Episode 状态
        self._update_episode_status(episode_id)

        logger.info(f"章节切分完成: episode_id={episode_id}, 章节数={len(chapters)}")

        return chapters

    def preview_segmentation(self, episode_id: int, for_preview: bool = False) -> Dict:
        """
        预览章节切分结果（不写入数据库，仅调用 AI 返回结果）

        用于审核：输出 MD 文档供人工核对章节标题与内容对应关系。

        Args:
            episode_id: Episode ID
            for_preview: 若 True，跳过状态检查（供调试脚本预览任意已转录的 episode）

        Returns:
            Dict: {"chapters": [...], "step1_reasoning": "..."} 章节列表与第一步推理
        """
        episode = self.db.query(Episode).filter(Episode.id == episode_id).first()
        if not episode:
            raise ValueError(f"Episode 不存在: episode_id={episode_id}")

        valid_statuses = [
            WorkflowStatus.TRANSCRIBED.value,
            WorkflowStatus.PROOFREAD.value,
            WorkflowStatus.SEGMENTED.value,  # 已分章也可预览（用于重新生成）
        ]
        if not for_preview and episode.workflow_status not in valid_statuses:
            raise ValueError(
                f"Episode 状态不允许: {WorkflowStatus(episode.workflow_status).label}"
            )

        cues = (
            self.db.query(TranscriptCue)
            .join(AudioSegment, AudioSegment.id == TranscriptCue.segment_id)
            .filter(AudioSegment.episode_id == episode_id)
            .order_by(TranscriptCue.start_time)
            .all()
        )
        if not cues:
            raise ValueError(f"Episode 没有转录内容: episode_id={episode_id}")

        transcript_text, use_sampling = self._build_transcript_text(cues)
        duration_minutes = episode.duration / 60
        max_chapters = 6 if duration_minutes >= 20 else (4 if duration_minutes >= 8 else 2)
        prompt_template = SEGMENTATION_PROMPT_SAMPLED if use_sampling else SEGMENTATION_PROMPT_FULL
        prompt = prompt_template.format(
            duration=f"{duration_minutes:.1f}",
            duration_seconds=f"{episode.duration:.0f}",
            max_chapters=max_chapters,
            transcript=transcript_text
        )

        response = self._call_ai_with_fallback(
            prompt=prompt,
            cues=cues,
            episode=episode,
            use_sampling=use_sampling
        )

        return {
            "chapters": [
                {
                    "title": ch.title,
                    "summary": ch.summary,
                    "start_time": ch.start_time,
                    "end_time": ch.end_time,
                    "reasoning": getattr(ch, "reasoning", None) or "",
                }
                for ch in response.chapters
            ],
            "step1_reasoning": getattr(response, "step1_reasoning", None) or "",
        }

    def _sample_cues_by_time(
        self,
        cues: List[TranscriptCue],
        max_cues: int = FALLBACK_MAX_CUES
    ) -> List[TranscriptCue]:
        """基于时间的均匀采样"""
        if len(cues) <= max_cues:
            return cues
        total_duration = cues[-1].start_time
        sample_interval = total_duration / max_cues
        sampled_cues = []
        last_sampled_time = -1
        for cue in cues:
            if cue.start_time - last_sampled_time >= sample_interval:
                sampled_cues.append(cue)
                last_sampled_time = cue.start_time
                if len(sampled_cues) >= max_cues:
                    break
        if sampled_cues and sampled_cues[-1].id != cues[-1].id:
            sampled_cues.append(cues[-1])
        logger.info(
            f"采样兜底: 原始 {len(cues)} 条 -> {len(sampled_cues)} 条, "
            f"时间 {sampled_cues[0].start_time:.0f}s - {sampled_cues[-1].start_time:.0f}s"
        )
        return sampled_cues

    def _build_transcript_text(
        self,
        cues: List[TranscriptCue]
    ) -> tuple[str, bool]:
        """
        构建 Transcript 文本（含时间戳）

        策略：始终传全量内容，不主动采样。采样仅在 API 失败时由 _call_ai_with_fallback 重试使用。

        Args:
            cues: TranscriptCue 列表

        Returns:
            Tuple[str, bool]: (格式化文本, 是否使用了采样)，此处恒为 (text, False)
        """
        lines = []
        for cue in cues:
            minutes = int(cue.start_time // 60)
            seconds = int(cue.start_time % 60)
            time_str = f"[{minutes:02d}:{seconds:02d}]"
            lines.append(f"{time_str} {cue.speaker}: {cue.text}")
        return "\n".join(lines), False

    def _call_ai_with_fallback(
        self,
        prompt: str,
        cues: List[TranscriptCue],
        episode: Episode,
        use_sampling: bool
    ) -> SegmentationResponse:
        """
        调用 AI 进行章节切分，带重试兜底。

        策略：单阶段 CoT 模式；失败且为 context 类错误时重试采样；最后单章节兜底。
        """
        try:
            response = self._call_ai_for_segmentation(prompt, total_duration=episode.duration)
            return SegmentationValidator.validate(response, total_duration=episode.duration)
        except Exception as e:
            error_str = str(e).lower()
            is_context_error = (
                "context" in error_str
                or "token" in error_str
                or "length" in error_str
                or "max_tokens" in error_str
                or "rate" in error_str
                or "timeout" in error_str
            )

            if not use_sampling and is_context_error:
                logger.warning(f"完整模式失败 ({e})，重试采样模式")
                sampled_cues = self._sample_cues_by_time(cues, FALLBACK_MAX_CUES)
                lines = []
                for cue in sampled_cues:
                    minutes = int(cue.start_time // 60)
                    seconds = int(cue.start_time % 60)
                    lines.append(f"[{minutes:02d}:{seconds:02d}] {cue.speaker}: {cue.text}")
                transcript_text = "\n".join(lines)
                duration_minutes = episode.duration / 60
                max_chapters = 6 if duration_minutes >= 20 else (4 if duration_minutes >= 8 else 2)
                retry_prompt = SEGMENTATION_PROMPT_SAMPLED.format(
                    duration=f"{duration_minutes:.1f}",
                    duration_seconds=f"{episode.duration:.0f}",
                    max_chapters=max_chapters,
                    transcript=transcript_text
                )
                try:
                    response = self._call_ai_for_segmentation(
                        retry_prompt, total_duration=episode.duration
                    )
                    return SegmentationValidator.validate(response, total_duration=episode.duration)
                except Exception as retry_e:
                    logger.warning(f"采样模式也失败: {retry_e}")

            logger.warning(f"AI 章节切分失败: {e}，使用兜底方案（单章节）")
            return self._create_fallback_response(episode)

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
        response: SegmentationResponse
    ) -> List[Chapter]:
        """
        创建 Chapter 记录

        Args:
            episode_id: Episode ID
            response: SegmentationResponse (Pydantic model)

        Returns:
            List[Chapter]: 创建的 Chapter 列表
        """
        chapters = []
        for index, chapter_data in enumerate(response.chapters):
            chapter = Chapter(
                episode_id=episode_id,
                chapter_index=index,
                title=chapter_data.title,
                summary=chapter_data.summary,
                start_time=chapter_data.start_time,
                end_time=chapter_data.end_time,
                status="completed",
                ai_model_used=f"{self.provider}:{self.structured_llm.model if self.structured_llm else 'unknown'}",
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

    def _call_ai_for_segmentation(self, prompt: str, total_duration: float) -> SegmentationResponse:
        """
        调用 StructuredLLM 进行章节切分

        Args:
            prompt: 提示词
            total_duration: 总时长（秒）

        Returns:
            SegmentationResponse: AI 返回的章节数据

        Raises:
            Exception: AI 调用失败（由上层捕获并使用兜底方案）
        """
        if not self.structured_llm:
            raise ValueError("StructuredLLM 未初始化")

        try:
            # Get structured output LLM
            structured_llm = self.structured_llm.with_structured_output(
                schema=SegmentationResponse
            )

            # Invoke with retry logic
            messages = [
                SystemMessage(content="你是一个专业的音频内容分析师。你擅长识别内容的语义结构，拒绝机械式时间切分，始终保持章节的语义完整性。对于短内容，你会减少切分；对于长内容，你会适当增加切分点，但绝不碎片化。"),
                HumanMessage(content=prompt)
            ]

            from app.services.ai.retry import ai_retry

            @ai_retry(max_retries=2, initial_delay=1.0)
            def call_llm_with_retry():
                return structured_llm.invoke(messages)

            result: SegmentationResponse = call_llm_with_retry()

            logger.info(f"AI 返回 {len(result.chapters)} 个章节")
            return result

        except Exception as e:
            logger.error(f"AI 调用失败: {e}")
            raise RuntimeError(f"章节切分 AI 调用失败: {e}") from e

    def _create_fallback_response(self, episode: Episode) -> SegmentationResponse:
        """
        创建兜底单章节响应（当 AI 失败时使用）

        Args:
            episode: Episode 对象

        Returns:
            SegmentationResponse: 包含单个章节的响应
        """
        from app.services.ai.schemas.segmentation_schema import Chapter

        total_duration = episode.duration
        fallback_chapter = Chapter(
            title=episode.title,  # 使用 episode.title
            summary=f"AI 章节切分失败，使用默认单章节。总时长: {total_duration / 60:.1f} 分钟。",
            start_time=0.0,
            end_time=total_duration
        )

        return SegmentationResponse(chapters=[fallback_chapter])

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
