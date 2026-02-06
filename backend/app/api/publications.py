"""
Publications API Routes

发布状态查询和重试端点。
"""
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import MOONSHOT_API_KEY, MOONSHOT_BASE_URL
from app.database import get_session
from app.enums.workflow_status import WorkflowStatus
from app.models import Episode, PublicationRecord
from app.schemas.publication import (
    PublicationRecordResponse,
    PublicationStatusResponse,
    RetryPublicationResponse,
)
from app.workflows.publisher import WorkflowPublisher


router = APIRouter()


def get_llm_client():
    """获取 LLM 客户端"""
    if MOONSHOT_API_KEY:
        from openai import OpenAI
        return OpenAI(api_key=MOONSHOT_API_KEY, base_url=MOONSHOT_BASE_URL)
    return None


# ==================== API Endpoints ====================


@router.get("/episodes/{episode_id}/publication-status", response_model=PublicationStatusResponse)
async def get_publication_status(
    episode_id: int,
    db: Session = Depends(get_session),
):
    """
    获取发布状态

    返回指定 Episode 的所有发布记录和统计摘要。
    """
    # 验证 Episode 存在
    episode = db.get(Episode, episode_id)
    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Episode not found: id={episode_id}"
        )

    # 查询发布记录
    records = (
        db.query(PublicationRecord)
        .filter(PublicationRecord.episode_id == episode_id)
        .order_by(PublicationRecord.created_at.desc())
        .all()
    )

    # 计算统计摘要
    summary = {
        "total": len(records),
        "success": sum(1 for r in records if r.status == "success"),
        "failed": sum(1 for r in records if r.status == "failed"),
        "pending": sum(1 for r in records if r.status == "pending"),
    }

    return PublicationStatusResponse(
        episode_id=episode_id,
        records=records,
        summary=summary,
    )


@router.get("/publications/{record_id}", response_model=PublicationRecordResponse)
async def get_publication_record(
    record_id: int,
    db: Session = Depends(get_session),
):
    """
    获取单条发布记录详情
    """
    record = db.get(PublicationRecord, record_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Publication record not found: id={record_id}"
        )

    return record


@router.post("/publications/{record_id}/retry", response_model=RetryPublicationResponse)
async def retry_publication(
    record_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
):
    """
    重试发布

    对失败的发布记录进行重试。
    """
    record = db.get(PublicationRecord, record_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Publication record not found: id={record_id}"
        )

    if record.status == "success":
        return RetryPublicationResponse(
            id=record_id,
            status=record.status,
            message="Publication already succeeded, no need to retry"
        )

    # 后台任务函数
    def retry_task():
        publisher = WorkflowPublisher(db)
        try:
            # 重新执行发布流程
            publisher.publish_workflow(record.episode_id)
        except Exception as e:
            db.rollback()
            raise e

    background_tasks.add_task(retry_task)

    return RetryPublicationResponse(
        id=record_id,
        status="pending",
        message="Retry scheduled"
    )
