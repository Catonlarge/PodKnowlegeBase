"""
SubtitleProofreadingService

Service for proofreading Whisper transcribed subtitles using LLM.
Scans for errors in proper nouns, linking, and punctuation, and provides corrections.

Migrated to use StructuredLLM with Pydantic validation and retry logic.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from sqlalchemy.orm import Session
from langchain_core.messages import SystemMessage, HumanMessage

from app.models import Episode, TranscriptCue, TranscriptCorrection, AudioSegment
from app.config import (
    MOONSHOT_API_KEY, MOONSHOT_BASE_URL, MOONSHOT_MODEL,
    AI_QUERY_TIMEOUT
)
from app.services.ai.structured_llm import StructuredLLM
from app.services.ai.schemas.proofreading_schema import ProofreadingResponse
from app.services.ai.validators.proofreading_validator import ProofreadingValidator

logger = logging.getLogger(__name__)

# Default AI provider
DEFAULT_AI_PROVIDER = "moonshot"

# Type alias for backward compatibility
if TYPE_CHECKING:
    from app.services.ai.schemas.proofreading_schema import CorrectionSuggestion as CorrectionSuggestionType
else:
    CorrectionSuggestionType = dict


@dataclass
class CorrectionResult:
    """Result of a proofreading scan operation."""
    total_cues: int
    corrected_count: int
    skipped_count: int  # cues that were already marked as corrected
    corrections: List[CorrectionSuggestionType]
    duration_seconds: float


@dataclass
class CorrectionSummary:
    """Summary statistics for proofreading corrections."""
    episode_id: int
    total_cues: int
    corrected_cues: int
    correction_rate: float
    common_errors: Dict[str, int]  # error type -> count


class SubtitleProofreadingService:
    """
    Subtitle proofreading service using StructuredLLM.

    Scans Whisper transcribed subtitles for errors and provides corrections.
    Supports batch processing, checkpoint recovery, and local replacement.

    Uses StructuredLLM with Pydantic validation for reliable structured output.
    """

    def __init__(
        self,
        db: Session,
        provider: str = DEFAULT_AI_PROVIDER,
        api_key: str = None,
        base_url: str = None,
        model: str = None
    ):
        """
        Initialize the proofreading service.

        Args:
            db: Database session
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
                from app.config import ZHIPU_API_KEY, ZHIPU_BASE_URL, ZHIPU_MODEL
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
                base_url=base_url
            )
            logger.info(f"SubtitleProofreadingService: Initialized {provider} StructuredLLM")
        except Exception as e:
            logger.error(f"Failed to initialize StructuredLLM: {e}")
            self.structured_llm = None

    def scan_and_correct(
        self,
        episode_id: int,
        batch_size: int = 50,
        apply: bool = True
    ) -> CorrectionResult:
        """
        Scan and correct subtitles for an episode.

        Args:
            episode_id: Episode ID
            batch_size: Number of cues to process per batch
            apply: Whether to automatically apply corrections to database

        Returns:
            CorrectionResult: Summary of corrections made

        Raises:
            ValueError: Episode not found or has no cues
        """
        # Get episode
        episode = self.db.get(Episode, episode_id)
        if not episode:
            raise ValueError(f"Episode not found: id={episode_id}")

        # Get all cues for this episode (through segments)
        cues = self.db.query(TranscriptCue).join(
            AudioSegment, TranscriptCue.segment_id == AudioSegment.id
        ).filter(
            AudioSegment.episode_id == episode_id
        ).order_by(TranscriptCue.start_time).all()

        if not cues:
            raise ValueError(f"No cues found for episode {episode_id}")

        start_time = datetime.now()

        # Filter out already corrected cues (for checkpoint recovery)
        uncorrected_cues = [c for c in cues if not c.is_corrected]
        skipped_count = len(cues) - len(uncorrected_cues)

        # Process all cues at once (no batching)
        all_corrections = []
        if uncorrected_cues:
            all_corrections = self._scan_batch(uncorrected_cues)

        # Apply corrections if requested
        if apply and all_corrections:
            corrected_count = self.apply_corrections(all_corrections, cues=uncorrected_cues)
        else:
            corrected_count = 0

        # Update episode proofreading status if corrections were applied
        if apply and corrected_count > 0:
            episode.proofread_status = "completed"
            episode.proofread_at = datetime.now()
            self.db.commit()

        duration = (datetime.now() - start_time).total_seconds()

        return CorrectionResult(
            total_cues=len(cues),
            corrected_count=corrected_count,
            skipped_count=skipped_count,
            corrections=all_corrections,
            duration_seconds=duration
        )

    def _scan_batch(self, cues: List[TranscriptCue]) -> List[CorrectionSuggestionType]:
        """
        Scan a batch of cues for corrections using StructuredLLM.

        Args:
            cues: List of TranscriptCue objects

        Returns:
            List[CorrectionSuggestion]: Corrections found by LLM
        """
        if not self.structured_llm:
            logger.warning("No StructuredLLM available, returning empty corrections")
            return []

        # Prepare subtitle list for LLM
        subtitle_list = []
        for cue in cues:
            subtitle_list.append({
                "cue_id": cue.id,
                "time": f"{int(cue.start_time // 60):02d}:{int(cue.start_time % 60):02d}",
                "text": cue.text
            })

        system_prompt = """你是一个专业的英语字幕校对专家。请检查以下英文字幕是否有识别错误。

**背景**：
- 这些字幕由 WhisperX 自动转录
- 可能包含：专有名词错误、连读误识别、标点错误

**任务**：
1. 识别需要修正的字幕
2. 只返回**需要修改**的内容（Patch Mode）
3. 如果所有字幕正确，返回空数组

**输出格式（JSON）**：
```json
{
  "corrections": [
    {
      "cue_id": <cue_id数字>,
      "original_text": "错误的文本",
      "corrected_text": "修正后的文本",
      "reason": "修正原因",
      "confidence": 0.95
    }
  ]
}
```

**注意**：
- cue_id 是数字标识符
- confidence 是 0-1 之间的置信度
- 只返回确实需要修正的内容"""

        user_prompt = f"""**字幕列表**：
{__import__('json').dumps(subtitle_list, ensure_ascii=False)}

请检查以上字幕，返回需要修正的内容（JSON格式）："""

        try:
            # Get structured output LLM
            structured_llm = self.structured_llm.with_structured_output(
                schema=ProofreadingResponse
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

            result: ProofreadingResponse = call_llm_with_retry()

            # Business validation
            valid_cue_ids = {c.id for c in cues}
            result = ProofreadingValidator.validate(
                result,
                valid_cue_ids=valid_cue_ids,
                total_cues=len(cues)
            )

            # Convert to dict format for backward compatibility
            suggestions = []
            for corr in result.corrections:
                suggestions.append({
                    "cue_id": corr.cue_id,
                    "original_text": corr.original_text,
                    "corrected_text": corr.corrected_text,
                    "reason": corr.reason,
                    "confidence": corr.confidence
                })

            logger.info(f"LLM found {len(suggestions)} corrections in batch of {len(cues)} cues")
            return suggestions

        except FutureTimeoutError:
            logger.error("AI proofreading timeout, returning empty corrections")
            return []
        except Exception as e:
            logger.error(f"AI proofreading failed: {e}, returning empty corrections")
            return []

    def apply_corrections(
        self,
        corrections: List[CorrectionSuggestionType],
        cues: List[TranscriptCue] = None
    ) -> int:
        """
        Apply corrections to the database.

        Args:
            corrections: List of correction suggestions (dict format from Pydantic model)
            cues: Original cues list for validation (optional, recommended)

        Returns:
            int: Number of corrections applied
        """
        # Build cue text mapping for validation
        cue_text_map = {cue.id: cue.text for cue in (cues or [])}
        applied_count = 0

        for correction in corrections:
            cue_id = correction["cue_id"] if isinstance(correction, dict) else correction.cue_id
            original_text = correction["original_text"] if isinstance(correction, dict) else correction.original_text
            corrected_text = correction["corrected_text"] if isinstance(correction, dict) else correction.corrected_text
            reason = correction["reason"] if isinstance(correction, dict) else correction.reason
            confidence = correction["confidence"] if isinstance(correction, dict) else correction.confidence

            cue = self.db.get(TranscriptCue, cue_id)
            if not cue:
                logger.warning(f"Cue {cue_id} not found, skipping")
                continue

            # Validate original_text matches database if cues provided
            if cue_text_map and original_text != cue.text:
                logger.error(
                    f"cue_id {cue_id} original_text mismatch!\n"
                    f"  DB: '{cue.text[:50]}...'\n"
                    f"  AI: '{original_text[:50]}...'\n"
                    f"  Skipping correction"
                )
                continue

            # Update cue
            cue.corrected_text = corrected_text
            cue.is_corrected = True

            # Create correction record using database original_text
            correction_record = TranscriptCorrection(
                cue_id=cue.id,
                original_text=cue.text,  # Use database value
                corrected_text=corrected_text,
                reason=reason,
                confidence=confidence,
                ai_model=f"{self.provider}:{self.structured_llm.model if self.structured_llm else 'unknown'}",
                applied=True
            )
            self.db.add(correction_record)
            applied_count += 1

        self.db.commit()
        logger.info(f"Applied {applied_count} corrections to database")
        return applied_count

    def get_correction_summary(self, episode_id: int) -> CorrectionSummary:
        """
        Get summary statistics for proofreading corrections.

        Args:
            episode_id: Episode ID

        Returns:
            CorrectionSummary: Summary statistics
        """
        episode = self.db.get(Episode, episode_id)
        if not episode:
            raise ValueError(f"Episode not found: id={episode_id}")

        # Get total cues
        total_cues = self.db.query(TranscriptCue).join(
            AudioSegment, TranscriptCue.segment_id == AudioSegment.id
        ).filter(
            AudioSegment.episode_id == episode_id
        ).count()

        # Get corrected cues
        corrected_cues = self.db.query(TranscriptCue).join(
            AudioSegment, TranscriptCue.segment_id == AudioSegment.id
        ).filter(
            AudioSegment.episode_id == episode_id,
            TranscriptCue.is_corrected == True
        ).count()

        # Get common error types
        corrections = self.db.query(TranscriptCorrection).join(
            TranscriptCue, TranscriptCorrection.cue_id == TranscriptCue.id
        ).join(
            AudioSegment, TranscriptCue.segment_id == AudioSegment.id
        ).filter(
            AudioSegment.episode_id == episode_id
        ).all()

        common_errors = {}
        for corr in corrections:
            reason = corr.reason or "未分类"
            common_errors[reason] = common_errors.get(reason, 0) + 1

        correction_rate = corrected_cues / total_cues if total_cues > 0 else 0.0

        return CorrectionSummary(
            episode_id=episode_id,
            total_cues=total_cues,
            corrected_cues=corrected_cues,
            correction_rate=correction_rate,
            common_errors=common_errors
        )

    def export_corrected_srt(self, episode_id: int, output_path: str) -> int:
        """
        Export corrected subtitles to SRT file.

        Args:
            episode_id: Episode ID
            output_path: Path to output SRT file

        Returns:
            int: Number of cues exported

        Raises:
            ValueError: Episode not found or has no cues
        """
        episode = self.db.get(Episode, episode_id)
        if not episode:
            raise ValueError(f"Episode not found: id={episode_id}")

        # Get all cues with effective text (corrected or original)
        cues = self.db.query(TranscriptCue).join(
            AudioSegment, TranscriptCue.segment_id == AudioSegment.id
        ).filter(
            AudioSegment.episode_id == episode_id
        ).order_by(TranscriptCue.start_time).all()

        if not cues:
            raise ValueError(f"No cues found for episode {episode_id}")

        # Write SRT file
        with open(output_path, 'w', encoding='utf-8') as f:
            for i, cue in enumerate(cues, 1):
                # Format timestamps as HH:MM:SS,mmm
                start_time = self._format_srt_time(cue.start_time)
                end_time = self._format_srt_time(cue.end_time)

                # Use effective text (corrected if available, otherwise original)
                text = cue.effective_text

                # Write subtitle entry
                f.write(f"{i}\n")
                f.write(f"{start_time} --> {end_time}\n")
                f.write(f"[{cue.speaker}] {text}\n")
                f.write("\n")

        logger.info(f"Exported {len(cues)} cues to {output_path}")
        return len(cues)

    def _format_srt_time(self, seconds: float) -> str:
        """
        Convert seconds to SRT timestamp format.

        Args:
            seconds: Time in seconds

        Returns:
            str: Formatted timestamp like "00:00:00,031"
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        milliseconds = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"
