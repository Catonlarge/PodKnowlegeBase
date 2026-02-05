"""
SubtitleProofreadingService

Service for proofreading Whisper transcribed subtitles using LLM.
Scans for errors in proper nouns, linking, and punctuation, and provides corrections.
"""
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from sqlalchemy.orm import Session
from openai import OpenAI

from app.models import Episode, TranscriptCue, TranscriptCorrection, AudioSegment
from app.config import MOONSHOT_API_KEY, MOONSHOT_BASE_URL, MOONSHOT_MODEL, AI_QUERY_TIMEOUT

logger = logging.getLogger(__name__)

# Default AI provider
DEFAULT_AI_PROVIDER = "moonshot"


@dataclass
class CorrectionSuggestion:
    """Individual correction suggestion from LLM."""
    cue_id: int
    original_text: str
    corrected_text: str
    reason: str  # e.g., "拼写错误", "专有名词", "连读误识别"
    confidence: float  # 0-1


@dataclass
class CorrectionResult:
    """Result of a proofreading scan operation."""
    total_cues: int
    corrected_count: int
    skipped_count: int  # cues that were already marked as corrected
    corrections: List[CorrectionSuggestion]
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
    Subtitle proofreading service using LLM.

    Scans Whisper transcribed subtitles for errors and provides corrections.
    Supports batch processing, checkpoint recovery, and local replacement.
    """

    def __init__(self, db: Session, llm_service=None):
        """
        Initialize the proofreading service.

        Args:
            db: Database session
            llm_service: LLM service (optional, defaults to OpenAI client)
        """
        self.db = db
        self.llm_service = llm_service

        # Initialize OpenAI client if no service provided
        if self.llm_service is None and MOONSHOT_API_KEY:
            try:
                self.llm_service = OpenAI(
                    api_key=MOONSHOT_API_KEY,
                    base_url=MOONSHOT_BASE_URL
                )
                logger.info("SubtitleProofreadingService: Initialized OpenAI Client")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")

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

        # Process in batches
        all_corrections = []
        for i in range(0, len(uncorrected_cues), batch_size):
            batch = uncorrected_cues[i:i + batch_size]
            batch_corrections = self._scan_batch(batch)
            all_corrections.extend(batch_corrections)

        # Apply corrections if requested
        if apply and all_corrections:
            self.apply_corrections(all_corrections)
            corrected_count = len(all_corrections)
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

    def _scan_batch(self, cues: List[TranscriptCue]) -> List[CorrectionSuggestion]:
        """
        Scan a batch of cues for corrections using LLM.

        Args:
            cues: List of TranscriptCue objects

        Returns:
            List[CorrectionSuggestion]: Corrections found by LLM
        """
        if not self.llm_service:
            logger.warning("No LLM service available, returning empty corrections")
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
{json.dumps(subtitle_list, ensure_ascii=False)}

请检查以上字幕，返回需要修正的内容（JSON格式）："""

        try:
            executor = ThreadPoolExecutor(max_workers=1)

            def call_ai():
                completion = self.llm_service.chat.completions.create(
                    model=MOONSHOT_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.3,
                )
                return completion.choices[0].message.content

            future = executor.submit(call_ai)
            response_text = future.result(timeout=AI_QUERY_TIMEOUT)
            executor.shutdown(wait=False)

            # Parse JSON response
            response_text = response_text.strip()
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()

            result = json.loads(response_text)
            corrections = result.get("corrections", [])

            # Convert to CorrectionSuggestion objects
            suggestions = []
            for corr in corrections:
                suggestions.append(CorrectionSuggestion(
                    cue_id=corr["cue_id"],
                    original_text=corr["original_text"],
                    corrected_text=corr["corrected_text"],
                    reason=corr.get("reason", ""),
                    confidence=corr.get("confidence", 0.8)
                ))

            logger.info(f"LLM found {len(suggestions)} corrections in batch of {len(cues)} cues")
            return suggestions

        except FutureTimeoutError:
            logger.error("AI proofreading timeout, returning empty corrections")
            executor.shutdown(wait=False)
            return []
        except Exception as e:
            logger.error(f"AI proofreading failed: {e}, returning empty corrections")
            return []

    def apply_corrections(self, corrections: List[CorrectionSuggestion]) -> int:
        """
        Apply corrections to the database.

        Args:
            corrections: List of correction suggestions

        Returns:
            int: Number of corrections applied
        """
        applied_count = 0

        for correction in corrections:
            cue = self.db.get(TranscriptCue, correction.cue_id)
            if not cue:
                logger.warning(f"Cue {correction.cue_id} not found, skipping")
                continue

            # Update cue
            cue.corrected_text = correction.corrected_text
            cue.is_corrected = True

            # Create correction record
            correction_record = TranscriptCorrection(
                cue_id=cue.id,
                original_text=correction.original_text,
                corrected_text=correction.corrected_text,
                reason=correction.reason,
                confidence=correction.confidence,
                ai_model=MOONSHOT_MODEL,
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
