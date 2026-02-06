"""
Episodes API Routes

Episode CRUD 操作和工作流触发端点。
"""
import hashlib
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config import MOONSHOT_API_KEY, MOONSHOT_BASE_URL
from app.database import get_session
from app.enums.workflow_status import WorkflowStatus
from app.models import Episode
from app.schemas.episode import (
    EpisodeCreate,
    EpisodeUpdate,
    EpisodeResponse,
    EpisodeDetailResponse,
    EpisodeListResponse,
    EpisodeWorkflowRequest,
    EpisodePublishRequest,
)
from app.workflows.runner import WorkflowRunner, create_or_get_episode
from app.workflows.publisher import WorkflowPublisher


router = APIRouter()


# ==================== Helper Functions ====================


def calculate_url_hash(url: str) -> str:
    """计算 URL 的 MD5 哈希值用于去重"""
    return hashlib.md5(url.encode()).hexdigest()


def get_llm_client():
    """获取 LLM 客户端（可选）"""
    if MOONSHOT_API_KEY:
        from openai import OpenAI
        return OpenAI(api_key=MOONSHOT_API_KEY, base_url=MOONSHOT_BASE_URL)
    return None


# ==================== API Endpoints ====================


@router.post("/episodes", response_model=EpisodeResponse, status_code=status.HTTP_201_CREATED)
async def create_episode(
    data: EpisodeCreate,
    db: Session = Depends(get_session),
):
    """
    创建新 Episode

    根据 URL 创建新的 Episode，自动检查去重（基于 URL hash）。
    如果 URL 已存在，返回现有 Episode。

    - **url**: YouTube/Bilibili 等 URL
    - **title**: 可选标题（如未提供将从元数据获取）
    """
    url_hash = calculate_url_hash(data.url)

    # 检查是否已存在
    existing = db.query(Episode).filter(Episode.file_hash == url_hash).first()
    if existing:
        return existing

    # 创建新 Episode
    episode = Episode(
        title=data.title or "",
        file_hash=url_hash,
        source_url=data.url,
        duration=0.0,  # 将在下载后更新
        workflow_status=WorkflowStatus.INIT.value,
    )
    db.add(episode)
    db.commit()
    db.refresh(episode)

    return episode


@router.get("/episodes", response_model=EpisodeListResponse)
async def list_episodes(
    status: Optional[int] = Query(None, description="工作流状态过滤 (0-7)"),
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(20, ge=1, le=100, description="每页数量"),
    db: Session = Depends(get_session),
):
    """
    获取 Episode 列表（分页）

    支持按工作流状态过滤和分页查询。
    """
    query = db.query(Episode)

    # 状态过滤
    if status is not None:
        if not 0 <= status <= 7:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status value: {status}. Must be between 0 and 7."
            )
        query = query.filter(Episode.workflow_status == status)

    # 计算总数
    total = query.count()

    # 分页查询
    offset = (page - 1) * limit
    items = query.order_by(Episode.created_at.desc()).offset(offset).limit(limit).all()

    # 计算总页数
    pages = (total + limit - 1) // limit if total > 0 else 0

    return EpisodeListResponse(
        total=total,
        page=page,
        limit=limit,
        pages=pages,
        items=items,
    )


@router.get("/episodes/{episode_id}", response_model=EpisodeDetailResponse)
async def get_episode(
    episode_id: int,
    db: Session = Depends(get_session),
):
    """
    获取 Episode 详情

    返回 Episode 的完整信息，包括关联数据统计。
    """
    episode = db.get(Episode, episode_id)
    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Episode not found: id={episode_id}"
        )

    # 转换为响应模型并计算统计
    response_data = EpisodeDetailResponse.model_validate(episode)
    response_data.segments_count = len(episode.segments)
    response_data.cues_count = len(episode.transcript_cues)
    response_data.chapters_count = len(episode.chapters)
    response_data.marketing_posts_count = len(episode.marketing_posts)

    return response_data


@router.patch("/episodes/{episode_id}", response_model=EpisodeResponse)
async def update_episode(
    episode_id: int,
    data: EpisodeUpdate,
    db: Session = Depends(get_session),
):
    """
    更新 Episode

    支持更新标题和 AI 摘要。
    """
    episode = db.get(Episode, episode_id)
    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Episode not found: id={episode_id}"
        )

    # 更新字段
    if data.title is not None:
        episode.title = data.title
    if data.ai_summary is not None:
        episode.ai_summary = data.ai_summary

    db.commit()
    db.refresh(episode)

    return episode


@router.delete("/episodes/{episode_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_episode(
    episode_id: int,
    db: Session = Depends(get_session),
):
    """
    删除 Episode

    级联删除所有关联数据（segments, cues, chapters, translations 等）。
    """
    episode = db.get(Episode, episode_id)
    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Episode not found: id={episode_id}"
        )

    db.delete(episode)
    db.commit()

    return None


@router.post("/episodes/{episode_id}/run", response_model=EpisodeResponse)
async def run_episode_workflow(
    episode_id: int,
    request: EpisodeWorkflowRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
):
    """
    触发主工作流（后台执行）

    执行完整的内容处理流程：
    1. 下载音频
    2. Whisper 转录
    3. LLM 字幕校对
    4. AI 语义分章
    5. 批量翻译
    6. 生成 Obsidian 文档

    支持断点续传，已完成的步骤会被跳过。
    使用 `force_restart=true` 强制从头开始。

    此端点立即返回，工作流在后台执行。
    """
    episode = db.get(Episode, episode_id)
    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Episode not found: id={episode_id}"
        )

    # 后台任务函数
    def run_workflow_task():
        runner = WorkflowRunner(db)
        try:
            runner.run_workflow(episode.source_url, force_restart=request.force_restart)
        except Exception as e:
            db.rollback()
            raise e

    background_tasks.add_task(run_workflow_task)

    return episode


@router.post("/episodes/{episode_id}/publish", response_model=EpisodeResponse)
async def publish_episode(
    episode_id: int,
    request: EpisodePublishRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
):
    """
    触发发布流程（后台执行）

    执行发布相关操作：
    1. 解析 Obsidian 文档中的用户修改
    2. 回填修改到数据库
    3. 生成营销文案（可选）
    4. 分发到各平台

    此端点立即返回，发布流程在后台执行。
    """
    episode = db.get(Episode, episode_id)
    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Episode not found: id={episode_id}"
        )

    if episode.workflow_status != WorkflowStatus.READY_FOR_REVIEW.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Episode must be in READY_FOR_REVIEW status. Current: {WorkflowStatus(episode.workflow_status).label}"
        )

    # 后台任务函数
    def publish_task():
        publisher = WorkflowPublisher(db)
        try:
            # 可选：生成营销文案
            if request.generate_marketing:
                llm_client = get_llm_client()
                if llm_client:
                    publisher.llm_client = llm_client
                    publisher.marketing_service.llm_service = llm_client

            publisher.publish_workflow(episode_id)
        except Exception as e:
            db.rollback()
            raise e

    background_tasks.add_task(publish_task)

    return episode
