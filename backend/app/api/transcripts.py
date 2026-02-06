"""
Transcripts API Routes

字幕查询端点，支持中英对照和章节过滤。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import Episode, TranscriptCue, AudioSegment, Translation
from app.schemas.transcript import (
    TranscriptCueResponse,
    TranscriptCueWithTranslationResponse,
    TranscriptListResponse,
    EffectiveTextResponse,
)


router = APIRouter()


# ==================== API Endpoints ====================


@router.get("/episodes/{episode_id}/transcripts", response_model=TranscriptListResponse)
async def list_transcripts(
    episode_id: int,
    chapter_id: Optional[int] = Query(None, description="章节过滤"),
    db: Session = Depends(get_session),
):
    """
    获取 Episode 的字幕列表（中英对照）

    返回指定 Episode 的所有字幕，可选择按章节过滤。
    每条字幕包含原始英文和中文翻译（如有）。
    """
    # 验证 Episode 存在
    episode = db.get(Episode, episode_id)
    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Episode not found: id={episode_id}"
        )

    # 构建查询：通过 segment 关联到 episode
    query = (
        db.query(TranscriptCue)
        .join(AudioSegment, TranscriptCue.segment_id == AudioSegment.id)
        .filter(AudioSegment.episode_id == episode_id)
    )

    # 章节过滤
    if chapter_id is not None:
        query = query.filter(TranscriptCue.chapter_id == chapter_id)

    # 按时间排序
    cues = query.order_by(TranscriptCue.start_time).all()

    # 加载翻译并构建响应
    result_items = []
    for cue in cues:
        translation = cue.get_translation("zh")
        cue_data = TranscriptCueWithTranslationResponse.model_validate(cue)
        cue_data.translation = translation
        result_items.append(cue_data)

    return TranscriptListResponse(
        episode_id=episode_id,
        total=len(result_items),
        items=result_items,
    )


@router.get("/cues/{cue_id}", response_model=TranscriptCueResponse)
async def get_cue(
    cue_id: int,
    db: Session = Depends(get_session),
):
    """
    获取单条字幕详情
    """
    cue = db.get(TranscriptCue, cue_id)
    if not cue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cue not found: id={cue_id}"
        )

    return cue


@router.get("/cues/{cue_id}/effective-text", response_model=EffectiveTextResponse)
async def get_cue_effective_text(
    cue_id: int,
    db: Session = Depends(get_session),
):
    """
    获取字幕的有效文本

    返回修正后的文本（如已修正）或原始文本（如未修正）。
    """
    cue = db.get(TranscriptCue, cue_id)
    if not cue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cue not found: id={cue_id}"
        )

    return EffectiveTextResponse(
        cue_id=cue_id,
        text=cue.effective_text,
        is_corrected=cue.is_corrected,
    )
