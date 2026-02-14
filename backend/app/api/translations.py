"""
Translations API Routes

翻译查询和修正端点。
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import MOONSHOT_API_KEY
from app.database import get_session
from app.models import Episode, Translation, TranscriptCue, AudioSegment
from app.schemas.translation import (
    TranslationUpdate,
    TranslationResponse,
    BatchTranslateRequest,
    BatchTranslateResponse,
)
from app.services.translation_service import TranslationService


router = APIRouter()


# ==================== API Endpoints ====================


@router.get("/translations/{translation_id}", response_model=TranslationResponse)
async def get_translation(
    translation_id: int,
    db: Session = Depends(get_session),
):
    """
    获取翻译详情
    """
    translation = db.get(Translation, translation_id)
    if not translation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Translation not found: id={translation_id}"
        )

    return translation


@router.patch("/translations/{translation_id}", response_model=TranslationResponse)
async def update_translation(
    translation_id: int,
    data: TranslationUpdate,
    db: Session = Depends(get_session),
):
    """
    修正翻译（手动编辑）

    更新翻译内容并自动设置 RLHF 标记。
    如果修改后的内容与原始 AI 翻译不同，is_edited 会自动设为 True。
    """
    translation = db.get(Translation, translation_id)
    if not translation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Translation not found: id={translation_id}"
        )

    # 更新翻译
    old_translation = translation.translation
    translation.translation = data.translation

    # 自动设置 is_edited 标记（RLHF）
    if translation.original_translation and data.translation != translation.original_translation:
        translation.is_edited = True

    db.commit()
    db.refresh(translation)

    return translation


@router.post("/episodes/{episode_id}/translations/batch-translate", response_model=BatchTranslateResponse)
async def batch_translate_episode(
    episode_id: int,
    request: BatchTranslateRequest,
    db: Session = Depends(get_session),
):
    """
    批量翻译 Episode

    对 Episode 中的所有字幕进行批量翻译。
    支持断点续传，已翻译的字幕会被跳过。
    使用 force=true 强制重新翻译。

    此操作可能需要较长时间，建议使用后台任务模式。
    """
    # 验证 Episode 存在
    episode = db.get(Episode, episode_id)
    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Episode not found: id={episode_id}"
        )

    # 检查 LLM 服务可用性
    if not MOONSHOT_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM service not available. Please configure MOONSHOT_API_KEY."
        )

    # 创建翻译服务（使用 config 中的 provider）
    service = TranslationService(db, provider="moonshot")

    # force=true 时先删除已有翻译
    if request.force:
        service.delete_translations_for_episode(episode_id, language_code=request.language_code)

    # 执行批量翻译（batch_translate 返回成功翻译数量）
    try:
        completed = service.batch_translate(
            episode_id,
            language_code=request.language_code
        )

        # 获取 episode 总 cue 数用于响应
        total = db.query(TranscriptCue).join(
            AudioSegment, TranscriptCue.segment_id == AudioSegment.id
        ).filter(AudioSegment.episode_id == episode_id).count()

        return BatchTranslateResponse(
            episode_id=episode_id,
            language_code=request.language_code,
            total=total,
            completed=completed,
            skipped=0,
            failed=0,
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Translation failed: {str(e)}"
        )
