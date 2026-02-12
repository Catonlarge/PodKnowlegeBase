"""
Translation Service - 翻译服务

负责批量翻译 TranscriptCue，支持：
1. 批量翻译（分批降级 + 重试策略）
2. 断点续传（跳过已完成的翻译）
3. RLHF 双文本存储（original_translation + translation）
4. 多语言支持（zh, ja, fr 等）
5. 错误处理和重试

Migrated to use StructuredLLM with Pydantic validation and retry logic.
"""
import json
import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime
from typing import List, Tuple, Dict, Optional

from sqlalchemy.orm import Session
from langchain_core.messages import SystemMessage, HumanMessage

from app.models import Episode, TranscriptCue, Translation, AudioSegment
from app.enums.workflow_status import WorkflowStatus
from app.enums.translation_status import TranslationStatus
from app.config import (
    MOONSHOT_API_KEY, MOONSHOT_BASE_URL, MOONSHOT_MODEL,
    ZHIPU_API_KEY, ZHIPU_BASE_URL, ZHIPU_MODEL,
    GEMINI_API_KEY, GEMINI_MODEL,
    MOONSHOT_TIMEOUT, ZHIPU_TIMEOUT, GEMINI_TIMEOUT,
    AI_TEMPERATURE_TRANSLATION
)
from app.services.ai.structured_llm import StructuredLLM
from app.services.ai.schemas.translation_schema import TranslationResponse

logger = logging.getLogger(__name__)


# ========================================================================
# 批次降级 + 重试配置
# ========================================================================

@dataclass
class BatchRetryConfig:
    """批次重试配置"""
    batch_size: int      # 批次大小
    max_retries: int     # 最大重试次数


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
    5. 分批降级 + 重试策略

    Uses StructuredLLM with Pydantic validation for reliable structured output.

    Attributes:
        db: 数据库会话
        provider: AI provider name (moonshot, zhipu, gemini)
        structured_llm: StructuredLLM instance
        BATCH_SIZE: 每批翻译数量（默认 50，已弃用，改用 BATCH_DEGRADATION_CONFIG）
    """

    # 每批翻译数量（避免 API 限流）- 已弃用，保留兼容性
    BATCH_SIZE = 50

    # 批次降级 + 重试配置（按降级顺序）
    # 设计原则：大批次多重试，小批次少重试
    BATCH_DEGRADATION_CONFIG = [
        BatchRetryConfig(batch_size=100, max_retries=2),
        BatchRetryConfig(batch_size=50, max_retries=2),
        BatchRetryConfig(batch_size=25, max_retries=1),
        BatchRetryConfig(batch_size=10, max_retries=1),
    ]
    MIN_BATCH_SIZE = 10

    def __init__(
        self,
        db: Session,
        provider: str = "moonshot",
        api_key: str = None,
        base_url: str = None,
        model: str = None
    ):
        """
        初始化翻译服务

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
                timeout = MOONSHOT_TIMEOUT
            elif provider == "zhipu":
                api_key = ZHIPU_API_KEY
                base_url = base_url or ZHIPU_BASE_URL
                model = model or ZHIPU_MODEL
                timeout = ZHIPU_TIMEOUT
            elif provider == "gemini":
                api_key = GEMINI_API_KEY
                model = model or GEMINI_MODEL
                timeout = GEMINI_TIMEOUT
            else:
                raise ValueError(f"Unsupported provider: {provider}")
        else:
            timeout = MOONSHOT_TIMEOUT if provider == "moonshot" else (
                ZHIPU_TIMEOUT if provider == "zhipu" else GEMINI_TIMEOUT
            )

        try:
            self.structured_llm = StructuredLLM(
                provider=provider,
                model=model,
                api_key=api_key,
                base_url=base_url,
                timeout=timeout,
                temperature=AI_TEMPERATURE_TRANSLATION
            )
            logger.info(f"TranslationService: Initialized {provider} StructuredLLM")
        except Exception as e:
            logger.error(f"Failed to initialize StructuredLLM: {e}")
            self.structured_llm = None

    def batch_translate(
        self,
        episode_id: int,
        language_code: str = "zh",
        enable_retry: bool = True
    ) -> int:
        """
        批量翻译 Episode 的所有 TranscriptCue（使用分批降级 + 重试策略）

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

        # 使用分批降级 + 重试策略
        success_count = self._batch_translate_with_degradation(pending_cues, language_code)

        logger.info(f"批量翻译完成: episode_id={episode_id}, 成功={success_count}/{len(pending_cues)}")

        # 更新 Episode 状态
        if success_count > 0:
            self._update_episode_status(episode_id)

        return success_count

    def _batch_translate_with_degradation(
        self,
        cues: List[TranscriptCue],
        language_code: str
    ) -> int:
        """
        使用分批降级 + 重试策略进行批量翻译

        Args:
            cues: 待翻译的 Cue 列表
            language_code: 语言代码

        Returns:
            int: 成功翻译的数量
        """
        total_cues = len(cues)
        success_count = 0
        current_config_index = 0  # 当前使用的配置索引

        # 遍历所有 Cue，按当前批次大小处理
        i = 0
        while i < total_cues:
            # 确定当前批次大小
            config = self.BATCH_DEGRADATION_CONFIG[current_config_index]
            batch_size = min(config.batch_size, total_cues - i)
            batch = cues[i:i + batch_size]

            logger.info(
                f"处理批次: Cue {i+1}-{i+batch_size}/{total_cues} "
                f"(batch_size={batch_size}, max_retries={config.max_retries})"
            )

            # 尝试翻译当前批次（带重试）
            success, saved_count, failed_cues = self._try_translate_batch_with_retry(
                batch, language_code, config
            )

            if success:
                # 批次成功，继续下一批
                success_count += saved_count
                i += batch_size
            else:
                # 批次失败，尝试降级
                if current_config_index < len(self.BATCH_DEGRADATION_CONFIG) - 1:
                    # 降级到下一个配置
                    current_config_index += 1
                    new_config = self.BATCH_DEGRADATION_CONFIG[current_config_index]
                    logger.warning(
                        f"批次 {batch_size} 失败，降级到 {new_config.batch_size} "
                        f"(max_retries={new_config.max_retries})"
                    )
                else:
                    # 已到最后一级，回退到批次重试（50条/批，5轮）
                    logger.warning("所有批次大小都失败，回退到批次重试（50条/批，5轮）")
                    # 移除 rollback()，依赖 _create_translation 的 UPDATE 逻辑
                    # 重复调用不会创建重复记录，重试时会更新已保存的记录
                    fallback_count = self._fallback_translate_one_by_one(batch, language_code)
                    success_count += fallback_count
                    i += batch_size

        return success_count

    def _try_translate_batch_with_retry(
        self,
        batch: List[TranscriptCue],
        language_code: str,
        config: BatchRetryConfig
    ) -> Tuple[bool, int, List[TranscriptCue]]:
        """
        尝试翻译单个批次（带重试）

        优化：只重试失败的条目，避免重复翻译已成功的内容

        Args:
            batch: 待翻译的 Cue 列表
            language_code: 语言代码
            config: 批次重试配置

        Returns:
            Tuple[success: bool, saved_count: int, failed_cues: List]
        """
        max_attempts = config.max_retries + 1  # +1 因为第一次不算重试

        # 记录已成功的 cue_id
        successful_ids = set()
        saved_count = 0

        for attempt in range(max_attempts):
            try:
                # 只翻译失败的条目
                failed_batch = [c for c in batch if c.id not in successful_ids]

                if not failed_batch:
                    # 全部成功
                    return True, saved_count, []

                logger.info(
                    f"第 {attempt + 1} 次尝试，翻译 {len(failed_batch)} 条"
                    f"（跳过已成功的 {len(successful_ids)} 条）"
                )

                # 调用 AI 批量翻译
                result = self._call_ai_for_batch(failed_batch, language_code)
                translations = result["translations"]

                # 保存翻译结果
                for trans in translations:
                    self._create_translation(
                        trans["cue_id"],
                        language_code,
                        trans["translation"]
                    )
                    successful_ids.add(trans["cue_id"])
                    saved_count += 1

                # 成功
                if attempt > 0:
                    logger.info(
                        f"批次 {config.batch_size} 在第 {attempt + 1} 次尝试成功"
                    )

                return True, saved_count, []

            except ValueError as e:
                # JSON 验证失败
                if attempt < max_attempts - 1:
                    logger.warning(
                        f"批次 {config.batch_size} 第 {attempt + 1} 次尝试失败: {e}，"
                        f"已成功 {len(successful_ids)} 条，准备重试剩余 {len(batch) - len(successful_ids)} 条..."
                    )
                    time.sleep(1)  # 等待 1 秒后重试
                    continue
                else:
                    logger.error(
                        f"批次 {config.batch_size} 重试 {config.max_retries} 次后仍失败: {e}"
                    )
                    failed_cues = [c for c in batch if c.id not in successful_ids]
                    return False, saved_count, failed_cues

            except Exception as e:
                # 其他异常（网络错误等）
                logger.error(f"批次 {config.batch_size} 发生异常: {e}")
                failed_cues = [c for c in batch if c.id not in successful_ids]
                return False, saved_count, failed_cues

        failed_cues = [c for c in batch if c.id not in successful_ids]
        return False, saved_count, failed_cues

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

        Raises:
            ValueError: 翻译内容为空或仅包含空白字符
        """
        # 边界处理: 验证翻译内容非空
        if not translated_text or not translated_text.strip():
            raise ValueError(f"翻译内容为空: cue_id={cue_id}, language_code={language_code}")

        # 边界处理: 限制翻译长度（防止数据库溢出）
        MAX_TRANSLATION_LENGTH = 10000  # 10k 字符
        if len(translated_text) > MAX_TRANSLATION_LENGTH:
            logger.warning(
                f"翻译过长 ({len(translated_text)} 字符)，"
                f"截断到 {MAX_TRANSLATION_LENGTH}: cue_id={cue_id}"
            )
            translated_text = translated_text[:MAX_TRANSLATION_LENGTH]

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

    def _fallback_translate_one_by_one(self, cues: List[TranscriptCue], language_code: str) -> int:
        """
        回退方案：批次重试（50条/批，最多5轮，不足50条也触发）

        根据决策要求：
        - 失败项收集到50条后批量重试
        - 循环5轮
        - 不足50条也触发重试
        - 5轮后仍失败的入库NULL（status='failed'）

        Args:
            cues: 待翻译的 Cue 列表
            language_code: 语言代码

        Returns:
            int: 成功翻译的数量
        """
        BATCH_RETRY_SIZE = 50
        max_retry_rounds = 5

        success_count = 0
        failed_items = [(cue, cue.text) for cue in cues]

        for round_num in range(max_retry_rounds):
            if not failed_items:
                break

            logger.info(
                f"第 {round_num + 1} 轮批次重试，待处理: {len(failed_items)} 条"
            )

            # 取出一批（最多50条，不足50条也触发）
            batch = failed_items[:BATCH_RETRY_SIZE]
            failed_items = failed_items[BATCH_RETRY_SIZE:]

            for cue, original_text in batch:
                try:
                    # 单条调用 AI（重试）
                    translated_text = self._translate_single_cue(cue, original_text, language_code)

                    # 保存成功翻译
                    self._create_translation(cue.id, language_code, translated_text)
                    success_count += 1

                except Exception as single_error:
                    logger.warning(f"  Cue {cue.id} 翻译失败: {single_error}，收集下一批重试")
                    failed_items.append((cue, original_text))

            self.db.flush()

        # 5轮后仍有失败项，入库 NULL
        if failed_items:
            logger.warning(f"5轮重试后仍有 {len(failed_items)} 条失败，入库NULL")
            for cue, original_text in failed_items:
                self._create_failed_translation(cue.id, language_code, str(original_text))

        return success_count

    def _translate_single_cue(self, cue: TranscriptCue, original_text: str, language_code: str) -> str:
        """
        翻译单条 Cue（用于批次重试）

        Args:
            cue: TranscriptCue 对象
            original_text: 原始文本
            language_code: 语言代码

        Returns:
            str: 翻译文本

        Raises:
            RuntimeError: 翻译失败
        """
        prompt = TRANSLATION_PROMPT.format(english_text=original_text)
        translated_text = self._call_ai_for_translation(prompt, language_code)
        return translated_text

    def _create_failed_translation(self, cue_id: int, language_code: str, original_text: str) -> None:
        """
        创建失败翻译记录（translation=NULL, status='failed'）

        Args:
            cue_id: TranscriptCue ID
            language_code: 语言代码
            original_text: 原始文本
        """
        translation = Translation(
            cue_id=cue_id,
            language_code=language_code,
            original_translation=None,  # NULL
            translation=None,  # NULL
            is_edited=False,
            translation_status=TranslationStatus.FAILED.value,
            translation_error=f"AI 翻译失败，已重试5轮",
            translation_retry_count=5,
            translation_started_at=datetime.now()
        )
        self.db.add(translation)
        self.db.flush()

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
                temperature=AI_TEMPERATURE_TRANSLATION,
            )

            # 边界处理: 检查 content 是否为 None
            content = completion.choices[0].message.content
            if content is None:
                raise ValueError("AI 返回了空响应 (content=None)")

            translated_text = content.strip()

            # 边界处理: 检查翻译是否为空字符串
            if not translated_text:
                raise ValueError("AI 返回了空白翻译")

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

    # ========================================================================
    # JSON 验证方法
    # ========================================================================

    def _validate_and_parse_translations(
        self,
        response_text: str,
        expected_cues: List[TranscriptCue]
    ) -> List[Dict]:
        """
        严格验证并解析翻译结果

        验证项：
        1. 格式验证：JSON 解析成功，包含 translations 字段
        2. 类型验证：字段类型正确
        3. 完整性验证：数量匹配，所有 cue_id 都存在
        4. 唯一性验证：无重复 cue_id
        5. 有效性验证：所有 cue_id 都在输入列表中

        Args:
            response_text: AI 返回的 JSON 文本
            expected_cues: 预期的 Cue 列表

        Returns:
            List[Dict]: 解析后的翻译列表

        Raises:
            ValueError: 任一验证失败，包含详细错误信息
        """
        # 清理 markdown 代码块标记
        cleaned_text = self._clean_json_response(response_text)

        # 1. 格式验证：JSON 解析
        try:
            result = json.loads(cleaned_text)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 解析失败: {e}") from e

        # 2. 结构验证：包含 translations 字段
        if "translations" not in result:
            raise ValueError("缺少 'translations' 字段")

        translations = result["translations"]

        # 3. 类型验证：translations 是列表
        if not isinstance(translations, list):
            raise ValueError("'translations' 不是列表类型")

        if not translations:
            raise ValueError("'translations' 列表为空")

        # 验证每条翻译的字段类型
        for trans in translations:
            if not isinstance(trans, dict):
                raise ValueError("翻译项不是字典类型")

            if "cue_id" not in trans:
                raise ValueError("缺少 'cue_id' 字段")

            if "translation" not in trans:
                raise ValueError("缺少 'translation' 字段")

            if not isinstance(trans["cue_id"], int):
                raise ValueError(f"'cue_id' 类型错误: {type(trans['cue_id'])}")

            if not isinstance(trans["translation"], str):
                raise ValueError(f"'translation' 类型错误: {type(trans['translation'])}")

        # 4. 唯一性验证：无重复 cue_id（在数量验证之前检查）
        returned_ids = [trans["cue_id"] for trans in translations]
        if len(returned_ids) != len(set(returned_ids)):
            seen = set()
            duplicates = []
            for cue_id in returned_ids:
                if cue_id in seen:
                    duplicates.append(cue_id)
                seen.add(cue_id)

            if duplicates:
                raise ValueError(f"重复的 cue_id: {duplicates}")

        # 5. 完整性验证：数量匹配
        expected_ids = {cue.id for cue in expected_cues}
        returned_ids_set = set(returned_ids)

        if len(returned_ids_set) < len(expected_ids):
            missing = expected_ids - returned_ids_set
            raise ValueError(f"缺少 {len(missing)} 条翻译: cue_ids {missing}")

        if len(returned_ids_set) > len(expected_ids):
            extra = returned_ids_set - expected_ids
            raise ValueError(f"返回了 {len(extra)} 条多余的翻译: cue_ids {extra}")

        # 6. 有效性验证：所有 cue_id 都在预期范围内
        invalid_ids = returned_ids_set - expected_ids
        if invalid_ids:
            raise ValueError(f"无效的 cue_id: {invalid_ids}")

        return translations

    def _clean_json_response(self, response_text: str) -> str:
        """
        清理 markdown 代码块标记，返回纯 JSON 文本

        Args:
            response_text: AI 返回的原始文本

        Returns:
            str: 清理后的 JSON 文本
        """
        text = response_text.strip()

        # 移除 ```json 开头
        if text.startswith("```json"):
            text = text[7:]
        # 移除 ``` 开头
        elif text.startswith("```"):
            text = text[3:]

        # 移除 ``` 结尾
        if text.endswith("```"):
            text = text[:-3]

        return text.strip()

    def _classify_validation_error(
        self,
        error: ValueError,
        batch: List[TranscriptCue]
    ) -> str:
        """
        分类验证错误类型

        Args:
            error: 验证错误
            batch: 当前批次

        Returns:
            str: "format" | "incomplete" | "error"
        """
        import re
        error_msg = str(error)

        # 不完整错误：缺少部分翻译（必须先检查，因为包含"缺少"）
        if re.search(r"缺少 \d+ 条翻译", error_msg):
            return "incomplete"

        # 格式错误：JSON 解析失败、缺少字段、类型错误
        if any(keyword in error_msg for keyword in [
            "JSON 解析失败",
            "缺少",  # 通用缺少错误
            "不是列表类型",
            "类型错误",
            "不是字典类型"
        ]):
            return "format"

        # 数据错误：无效 cue_id、重复 cue_id
        if any(keyword in error_msg for keyword in [
            "无效的 cue_id",
            "重复的 cue_id",
            "多余的翻译"
        ]):
            return "error"

        # 默认为格式错误
        return "format"

    def _call_ai_for_batch(
        self,
        cues: List[TranscriptCue],
        language_code: str
    ) -> Dict:
        """
        调用 AI 批量翻译（使用 StructuredLLM）

        Args:
            cues: 待翻译的 Cue 列表
            language_code: 语言代码

        Returns:
            Dict: AI 返回的翻译结果字典

        Raises:
            ValueError: StructuredLLM 未初始化或验证失败
        """
        if not self.structured_llm:
            raise ValueError("StructuredLLM 未初始化")

        # 准备字幕数据
        subtitles_data = [
            {"cue_id": cue.id, "text": cue.text}
            for cue in cues
        ]

        # 构建批量翻译 prompt
        system_prompts = {
            "zh": "你是一名专业的英汉翻译专家。请将以下英文字幕翻译成准确、自然的中文。",
            "ja": "あなたはプロの英日翻訳者です。以下の英語字幕を自然な日本語に翻訳してください。",
            "fr": "Vous êtes un traducteur professionnel anglais-français. Traduisez les sous-titres anglais suivants en français naturel.",
            "ko": "당신은 전문 영한 번역가입니다. 다음 영어 자막을 자연스러운 한국어로 번역하세요.",
            "es": "Eres un traductor profesional inglés-español. Traduce los subtítulos ingleses siguientes a español natural.",
            "de": "Sie sind ein professioneller Übersetzer für Englisch-Deutsch. Übersetzen Sie die folgenden englischen Untertitel in natürliches Deutsch.",
        }
        system_prompt = system_prompts.get(language_code, system_prompts["zh"])

        # 准备有效的 cue_id 集合用于验证
        valid_cue_ids = {cue.id for cue in cues}

        user_prompt = f"""请将以下 {len(cues)} 条英文字幕翻译成目标语言。

**要求**：
1. 保持原意准确
2. 符合目标语言表达习惯
3. 必须为每一条字幕提供翻译
4. cue_id 和 original_text 必须与输入完全一致

**输入字幕**：
```json
{__import__('json').dumps(subtitles_data, ensure_ascii=False, separators=(',', ':'))}
```

请返回符合以下 JSON 格式的翻译结果：
```json
{{
  "translations": [
    {{
      "cue_id": 7021,
      "original_text": "Hello, how are you?",
      "translated_text": "你好，你好吗？"
    }}
  ]
}}
```

注意：必须返回完整的 JSON 对象，包含所有 {len(cues)} 条字幕的翻译。"""

        logger.info(f"调用 AI 批量翻译 {len(cues)} 条字幕...")

        try:
            # Get structured output LLM
            structured_llm = self.structured_llm.with_structured_output(
                schema=TranslationResponse
            )

            # Invoke with retry logic
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]

            from app.services.ai.retry import ai_retry

            @ai_retry(max_retries=2, initial_delay=1.0)
            def call_llm_with_retry():
                return structured_llm.invoke(messages)

            start_time = time.time()
            result: TranslationResponse = call_llm_with_retry()
            elapsed_time = time.time() - start_time

            logger.info(f"  AI 响应完成，耗时 {elapsed_time:.1f} 秒")

            # 业务验证：确保所有 cue_id 有效且完整
            translations = self._validate_translation_response(result, valid_cue_ids, cues)

            return {"translations": translations}

        except Exception as e:
            logger.error(f"AI 批量翻译调用失败: {e}")
            # 边界处理: 清理未提交的数据，避免状态残留
            self.db.rollback()
            raise  # 重新抛出异常，由上层重试逻辑处理

    def _validate_translation_response(
        self,
        response: TranslationResponse,
        valid_cue_ids: set,
        cues: List[TranscriptCue]
    ) -> List[Dict]:
        """
        验证 TranslationResponse 并转换为字典格式

        Args:
            response: TranslationResponse Pydantic 模型
            valid_cue_ids: 有效的 cue_id 集合
            cues: 原始 Cue 列表

        Returns:
            List[Dict]: 转换后的翻译列表

        Raises:
            ValueError: 验证失败
        """
        translations = []

        # 构建原始 cue 文本映射
        cue_text_map = {cue.id: cue.text for cue in cues}

        # 构建文本到 cue_id 的反向映射（处理重复文本）
        from collections import defaultdict
        text_to_cue_ids = defaultdict(list)
        for cue in cues:
            text_to_cue_ids[cue.text].append(cue.id)

        # 统计变量
        misalignment_count = 0
        duplicate_text_count = 0

        for item in response.translations:
            # 验证 cue_id 在有效范围内
            if item.cue_id not in valid_cue_ids:
                raise ValueError(f"无效的 cue_id: {item.cue_id}")

            # 验证 original_text 与原始文本匹配
            original_text = cue_text_map.get(item.cue_id, "")
            if item.original_text != original_text:
                # 如果不匹配，检查是否是错位问题
                logger.warning(
                    f"cue_id {item.cue_id} 的 original_text 不匹配！\n"
                    f"  期望: '{original_text[:50]}...'\n"
                    f"  实际: '{item.original_text[:50]}...'"
                )

                # 尝试通过 original_text 找到正确的 cue_id
                correct_cue_ids = text_to_cue_ids.get(item.original_text)
                if correct_cue_ids:
                    # 区分单匹配和多匹配场景
                    if len(correct_cue_ids) == 1:
                        # 场景 1: 唯一匹配，真正的错位
                        correct_cue_id = correct_cue_ids[0]
                        logger.debug(
                            f"  通过 original_text 找到唯一匹配: cue_id={correct_cue_id}"
                        )
                    else:
                        # 场景 2: 重复文本，取第一个
                        correct_cue_id = correct_cue_ids[0]
                        duplicate_text_count += 1
                        logger.warning(
                            f"  original_text 对应 {len(correct_cue_ids)} 个重复 cue_id: {correct_cue_ids}\n"
                            f"  将使用第一个: cue_id={correct_cue_id}（翻译内容相同，不影响结果）"
                        )

                    if correct_cue_id != item.cue_id:
                        misalignment_count += 1
                        logger.error(
                            f"  检测到错位: LLM 返回 cue_id={item.cue_id}，修复为 cue_id={correct_cue_id}"
                        )

                        # 边界处理: 检查是否与已添加的 cue_id 重复（双重错位检测）
                        if any(t["cue_id"] == correct_cue_id for t in translations):
                            raise ValueError(
                                f"修复错位时发现重复 cue_id={correct_cue_id}，"
                                f"可能存在双重错位，拒绝整个批次"
                            )

                        # 修复：保存到正确的 cue_id
                        translations.append({
                            "cue_id": correct_cue_id,
                            "translation": item.translated_text
                        })
                        continue

                # 无法找到匹配 - 这可能是 LLM 错误，拒绝此翻译
                # 计算文本相似度，如果是轻微差异（如标点、空格），可以接受
                original_lower = original_text.lower().strip()
                item_lower = item.original_text.lower().strip()

                # 检查是否是子串关系（允许 80% 相似度）
                is_substring = False
                if len(item_lower) > 0 and len(original_lower) > 0:
                    if item_lower in original_lower or original_lower in item_lower:
                        similarity = max(len(item_lower), len(original_lower)) / min(len(item_lower), len(original_lower))
                        if similarity <= 1.25:  # 长度差异小于 25%
                            is_substring = True

                if is_substring:
                    # 轻微差异，接受 LLM 的映射
                    logger.debug(f"  original_text 有轻微差异但可接受，使用 LLM 返回的 cue_id={item.cue_id}")
                else:
                    # 严重不匹配，拒绝
                    raise ValueError(
                        f"cue_id {item.cue_id} 的 original_text 严重不匹配且无法找到正确的映射！\n"
                        f"  期望: '{original_text[:100]}...'\n"
                        f"  实际: '{item.original_text[:100]}...'"
                    )

            translations.append({
                "cue_id": item.cue_id,
                "translation": item.translated_text
            })

        # 输出统计摘要
        if misalignment_count > 0 or duplicate_text_count > 0:
            logger.info(
                f"验证摘要: 修复 {misalignment_count} 处错位，"
                f"处理 {duplicate_text_count} 处重复文本"
            )

        # 验证完整性：所有 cue_id 都有翻译
        returned_ids = {t["cue_id"] for t in translations}
        missing_ids = valid_cue_ids - returned_ids
        if missing_ids:
            raise ValueError(f"缺少 {len(missing_ids)} 条翻译: cue_ids {missing_ids}")

        return translations
