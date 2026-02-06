"""
Chapters API Routes

章节查询端点。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import Episode, Chapter, TranscriptCue
from app.schemas.chapter import (
    ChapterResponse,
    ChapterDetailResponse,
    ChapterListResponse,
)


router = APIRouter()


# ==================== API Endpoints ====================


@router.get("/episodes/{episode_id}/chapters", response_model=ChapterListResponse)
async def list_chapters(
    episode_id: int,
    db: Session = Depends(get_session),
):
    """
    获取 Episode 的章节列表

    返回指定 Episode 的所有 AI 语义分章，按章节序号排序。
    """
    # 验证 Episode 存在
    episode = db.get(Episode, episode_id)
    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Episode not found: id={episode_id}"
        )

    # 查询章节
    chapters = (
        db.query(Chapter)
        .filter(Chapter.episode_id == episode_id)
        .order_by(Chapter.chapter_index)
        .all()
    )

    return ChapterListResponse(
        episode_id=episode_id,
        total=len(chapters),
        items=chapters,
    )


@router.get("/chapters/{chapter_id}", response_model=ChapterDetailResponse)
async def get_chapter(
    chapter_id: int,
    db: Session = Depends(get_session),
):
    """
    获取章节详情

    返回章节的完整信息，包括字幕数量统计。
    """
    chapter = db.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chapter not found: id={chapter_id}"
        )

    # 转换为响应模型并计算统计
    response_data = ChapterDetailResponse.model_validate(chapter)

    # 计算关联的字幕数量
    cues_count = (
        db.query(TranscriptCue)
        .filter(TranscriptCue.chapter_id == chapter_id)
        .count()
    )
    response_data.cues_count = cues_count

    return response_data


@router.get("/chapters/{chapter_id}/cues", response_model=ChapterListResponse)
async def get_chapter_cues(
    chapter_id: int,
    db: Session = Depends(get_session),
):
    """
    获取章节内的字幕列表

    返回属于指定章节的所有字幕。
    """
    # 验证 Chapter 存在
    chapter = db.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chapter not found: id={chapter_id}"
        )

    # 查询章节内的字幕
    cues = (
        db.query(TranscriptCue)
        .filter(TranscriptCue.chapter_id == chapter_id)
        .order_by(TranscriptCue.start_time)
        .all()
    )

    return {
        "chapter_id": chapter_id,
        "total": len(cues),
        "items": cues,
    }
