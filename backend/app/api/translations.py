"""
Translations API Routes

翻译查询和修正端点。
"""
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import MOONSHOT_API_KEY, MOONSHOT_BASE_URL
from app.database import get_session
from app.models import Episode, Translation
from app.schemas.translation import (
    TranslationUpdate,
    TranslationResponse,
    BatchTranslateRequest,
    BatchTranslateResponse,
)
from app.services.translation_service import TranslationService


router = APIRouter()


def get_llm_client():
    """获取 LLM 客户端"""
    if MOONSHOT_API_KEY:
        from openai import OpenAI
        return OpenAI(api_key=MOONSHOT_API_KEY, base_url=MOONSHOT_BASE_URL)
    return None


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
    llm_client = get_llm_client()
    if not llm_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM service not available. Please configure MOONSHOT_API_KEY."
        )

    # 创建翻译服务
    service = TranslationService(db, llm_service=llm_client)

    # 执行批量翻译
    try:
        result = service.batch_translate(
            episode_id,
            language_code=request.language_code,
            force=request.force
        )

        return BatchTranslateResponse(
            episode_id=episode_id,
            language_code=request.language_code,
            total=result.total,
            completed=result.completed,
            skipped=result.skipped,
            failed=result.failed,
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Translation failed: {str(e)}"
        )
