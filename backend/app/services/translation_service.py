"""
Translation Service - 翻译服务

负责批量翻译 TranscriptCue，支持：
1. 批量翻译（每批50条，避免 API 限流）
2. 断点续传（跳过已完成的翻译）
3. RLHF 双文本存储（original_translation + translation）
4. 多语言支持（zh, ja, fr 等）
5. 错误处理和重试
"""
import logging
import time
from datetime import datetime
from typing import List

from sqlalchemy.orm import Session

from app.models import Episode, TranscriptCue, Translation, AudioSegment
from app.services.ai.ai_service import AIService
from app.enums.workflow_status import WorkflowStatus
from app.enums.translation_status import TranslationStatus

logger = logging.getLogger(__name__)


# Translation Prompt 模板
TRANSLATION_PROMPT = """
你是一名专业的英汉翻译专家。请将以下英文句子翻译成**中文**。

**要求：**
1. 保持原意准确
2. 符合中文表达习惯
3. 口语化，自然流畅
4. 只返回翻译结果，不要解释

**英文：**
{english_text}
"""


class TranslationService:
    """
    翻译服务

    负责：
    1. 批量翻译 TranscriptCue
    2. RLHF 双文本存储（original_translation + translation）
    3. 断点续传（跳过已完成）
    4. 多语言支持（zh, ja, fr 等）

    Attributes:
        db: 数据库会话
        ai_service: AI 服务实例
        BATCH_SIZE: 每批翻译数量（默认 50）
    """

    # 每批翻译数量（避免 API 限流）
    BATCH_SIZE = 50

    def __init__(self, db: Session, ai_service: AIService):
        """
        初始化翻译服务

        Args:
            db: 数据库会话
            ai_service: AI 服务实例
        """
        self.db = db
        self.ai_service = ai_service

    def batch_translate(
        self,
        episode_id: int,
        language_code: str = "zh",
        enable_retry: bool = True
    ) -> int:
        """
        批量翻译 Episode 的所有 TranscriptCue

        Args:
            episode_id: Episode ID
            language_code: 语言代码 ('zh', 'ja', 'fr', etc.)
            enable_retry: 是否重试失败的翻译

        Returns:
            int: 成功翻译的 Cue 数量
        """
        logger.info(f"开始批量翻译: episode_id={episode_id}, language_code={language_code}")

        # 获取待翻译的 Cue 列表（断点续传）
        pending_cues = self._get_pending_cues(episode_id, language_code)

        if not pending_cues:
            logger.info(f"没有待翻译的 Cue: episode_id={episode_id}, language_code={language_code}")
            return 0

        success_count = 0
        total_cues = len(pending_cues)

        # 分批处理
        for i in range(0, total_cues, self.BATCH_SIZE):
            batch = pending_cues[i:i + self.BATCH_SIZE]
            logger.info(f"处理批次 {i // self.BATCH_SIZE + 1}: Cue {i+1}-{min(i + self.BATCH_SIZE, total_cues)}/{total_cues}")

            for cue in batch:
                try:
                    self.translate_cue(cue, language_code)
                    success_count += 1
                    # API 调用之间添加延迟，避免限流（每次翻译后暂停 0.5 秒）
                    time.sleep(0.5)
                except Exception as e:
                    logger.error(f"翻译失败: cue_id={cue.id}, error={e}")
                    # 错误已在 translate_cue 中记录，继续处理下一个
                    # 失败后也添加延迟，避免连续失败触发限流
                    time.sleep(1)

        logger.info(f"批量翻译完成: episode_id={episode_id}, 成功={success_count}/{total_cues}")

        # 更新 Episode 状态
        if success_count > 0:
            self._update_episode_status(episode_id)

        return success_count

    def translate_cue(
        self,
        cue: TranscriptCue,
        language_code: str
    ) -> Translation:
        """
        翻译单个 Cue

        Args:
            cue: TranscriptCue 对象
            language_code: 语言代码

        Returns:
            Translation: 创建的 Translation 对象

        Raises:
            RuntimeError: 翻译失败
        """
        logger.debug(f"翻译 Cue: cue_id={cue.id}, text='{cue.text[:30]}...'")

        # 查找或创建 Translation 记录
        translation = self.db.query(Translation).filter(
            Translation.cue_id == cue.id,
            Translation.language_code == language_code
        ).first()

        if translation is None:
            translation = Translation(
                cue_id=cue.id,
                language_code=language_code,
                translation_status=TranslationStatus.PROCESSING.value,
                translation_started_at=datetime.now()
            )
            self.db.add(translation)
            self.db.flush()
        else:
            # 更新状态为 processing
            translation.translation_status = TranslationStatus.PROCESSING.value
            translation.translation_started_at = datetime.now()
            translation.translation_retry_count += 1
            self.db.flush()

        try:
            # 调用 AI 翻译（直接调用 API，绕过 AIService 的 JSON 解析）
            prompt = TRANSLATION_PROMPT.format(english_text=cue.text)
            translated_text = self._call_ai_for_translation(prompt, language_code)

            # 创建/更新 Translation 记录
            translation = self._create_translation(cue.id, language_code, translated_text)

            logger.debug(f"翻译成功: cue_id={cue.id}")
            return translation

        except Exception as e:
            # 记录错误
            translation.translation_status = TranslationStatus.FAILED.value
            translation.translation_error = str(e)
            self.db.flush()

            logger.error(f"翻译失败: cue_id={cue.id}, error={e}")
            raise RuntimeError(f"翻译失败: {e}") from e

    def _get_pending_cues(
        self,
        episode_id: int,
        language_code: str
    ) -> List[TranscriptCue]:
        """
        获取待翻译的 Cue 列表（断点续传）

        待翻译条件：
        1. 没有对应语言的 Translation 记录
        2. Translation 状态为 pending 或 failed

        Args:
            episode_id: Episode ID
            language_code: 语言代码

        Returns:
            List[TranscriptCue]: 待翻译的 Cue 列表
        """
        # 获取 Episode 的所有 TranscriptCue
        cues = self.db.query(TranscriptCue).join(
            AudioSegment, TranscriptCue.segment_id == AudioSegment.id
        ).filter(
            AudioSegment.episode_id == episode_id
        ).order_by(TranscriptCue.start_time).all()

        if not cues:
            return []

        # 获取已完成的 Cue ID
        completed_cue_ids = self.db.query(Translation.cue_id).filter(
            Translation.language_code == language_code,
            Translation.translation_status == TranslationStatus.COMPLETED.value
        ).all()

        completed_ids = {cue_id for (cue_id,) in completed_cue_ids}

        # 返回未完成的 Cue
        pending_cues = [cue for cue in cues if cue.id not in completed_ids]

        logger.info(f"待翻译 Cue 数量: {len(pending_cues)}/{len(cues)}")
        return pending_cues

    def _create_translation(
        self,
        cue_id: int,
        language_code: str,
        translated_text: str
    ) -> Translation:
        """
        创建或更新 Translation 记录（RLHF 双文本）

        Args:
            cue_id: TranscriptCue ID
            language_code: 语言代码
            translated_text: 翻译文本

        Returns:
            Translation: 创建或更新的对象
        """
        # 查找现有记录
        translation = self.db.query(Translation).filter(
            Translation.cue_id == cue_id,
            Translation.language_code == language_code
        ).first()

        if translation is None:
            # 创建新记录（original_translation 和 translation 相同）
            translation = Translation(
                cue_id=cue_id,
                language_code=language_code,
                translation=translated_text,
                original_translation=translated_text,  # RLHF 双文本设计
                is_edited=False,
                translation_status=TranslationStatus.COMPLETED.value,
                translation_completed_at=datetime.now()
            )
            self.db.add(translation)
        else:
            # 更新现有记录
            translation.translation = translated_text
            # 保持 original_translation 不变（首次设置后不再修改）
            if translation.original_translation is None:
                translation.original_translation = translated_text
            translation.translation_status = TranslationStatus.COMPLETED.value
            translation.translation_error = None
            translation.translation_completed_at = datetime.now()

        self.db.flush()
        return translation

    def _call_ai_for_translation(self, prompt: str, language_code: str) -> str:
        """
        直接调用 AI API 进行翻译（返回原始文本）

        绕过 AIService.query() 的 JSON 解析，直接获取翻译文本

        Args:
            prompt: 提示词
            language_code: 语言代码

        Returns:
            str: AI 返回的翻译文本

        Raises:
            RuntimeError: AI 调用失败
        """
        from openai import OpenAI
        from app.config import MOONSHOT_API_KEY, MOONSHOT_BASE_URL, MOONSHOT_MODEL

        if not MOONSHOT_API_KEY:
            raise ValueError("MOONSHOT_API_KEY 未设置")

        try:
            client = OpenAI(
                api_key=MOONSHOT_API_KEY,
                base_url=MOONSHOT_BASE_URL
            )

            # 根据语言代码调整 system prompt
            system_prompts = {
                "zh": "你是一名专业的英汉翻译专家。请将英文翻译成准确、自然的中文。",
                "ja": "あなたはプロの英日翻訳者です。英語を自然な日本語に翻訳してください。",
                "fr": "Vous êtes un traducteur professionnel anglais-français. Traduisez l'anglais en français naturel.",
                "ko": "당신은 전문 영한 번역가입니다. 영어를 자연스러운 한국어로 번역하세요.",
                "es": "Eres un traductor profesional inglés-español. Traduce el inglés a español natural.",
                "de": "Sie sind ein professioneller Übersetzer für Englisch-Deutsch. Übersetzen Sie Englisch auf natürliches Deutsch.",
            }
            system_prompt = system_prompts.get(language_code, system_prompts["zh"])

            logger.debug(f"调用 Moonshot API 进行翻译 (model={MOONSHOT_MODEL}, lang={language_code})")

            completion = client.chat.completions.create(
                model=MOONSHOT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
            )

            translated_text = completion.choices[0].message.content.strip()
            logger.debug(f"AI 翻译响应: {translated_text[:50]}...")
            return translated_text

        except Exception as e:
            logger.error(f"AI 翻译调用失败: {e}")
            raise RuntimeError(f"翻译 AI 调用失败: {e}") from e

    def _update_episode_status(self, episode_id: int) -> None:
        """
        更新 Episode.workflow_status 为 TRANSLATED

        Args:
            episode_id: Episode ID
        """
        episode = self.db.query(Episode).filter(Episode.id == episode_id).first()

        if episode and episode.workflow_status == WorkflowStatus.SEGMENTED.value:
            episode.workflow_status = WorkflowStatus.TRANSLATED.value
            self.db.flush()
            logger.info(f"Episode 状态已更新: id={episode_id}, status=TRANSLATED")
