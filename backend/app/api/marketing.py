"""
Marketing API Routes

营销文案生成和查询端点。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config import MOONSHOT_API_KEY, MOONSHOT_BASE_URL
from app.database import get_session
from app.models import Episode, MarketingPost
from app.schemas.marketing import (
    MarketingPostResponse,
    GenerateMarketingRequest,
    MarketingPostListResponse,
)
from app.services.marketing_service import MarketingService


router = APIRouter()


def get_llm_client():
    """获取 LLM 客户端"""
    if MOONSHOT_API_KEY:
        from openai import OpenAI
        return OpenAI(api_key=MOONSHOT_API_KEY, base_url=MOONSHOT_BASE_URL)
    return None


# ==================== API Endpoints ====================


@router.get("/episodes/{episode_id}/marketing-posts", response_model=MarketingPostListResponse)
async def list_marketing_posts(
    episode_id: int,
    platform: Optional[str] = Query(None, description="平台过滤"),
    angle_tag: Optional[str] = Query(None, description="角度标签过滤"),
    db: Session = Depends(get_session),
):
    """
    获取营销文案列表

    返回指定 Episode 的所有营销文案，支持按平台和角度过滤。
    """
    # 验证 Episode 存在
    episode = db.get(Episode, episode_id)
    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Episode not found: id={episode_id}"
        )

    # 构建查询
    query = db.query(MarketingPost).filter(MarketingPost.episode_id == episode_id)

    if platform:
        query = query.filter(MarketingPost.platform == platform)
    if angle_tag:
        query = query.filter(MarketingPost.angle_tag == angle_tag)

    posts = query.order_by(MarketingPost.created_at.desc()).all()

    return MarketingPostListResponse(
        episode_id=episode_id,
        total=len(posts),
        items=posts,
    )


@router.post("/episodes/{episode_id}/marketing-posts/generate", response_model=MarketingPostListResponse, status_code=status.HTTP_201_CREATED)
async def generate_marketing_posts(
    episode_id: int,
    request: GenerateMarketingRequest,
    db: Session = Depends(get_session),
):
    """
    生成营销文案

    使用 AI 为 Episode 生成营销文案。
    支持指定平台和内容角度。

    需要配置 LLM 服务 (MOONSHOT_API_KEY)。
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

    # 创建营销服务
    service = MarketingService(db, llm_service=llm_client)

    # 生成营销文案
    try:
        # 使用实际存在的方法生成文案
        marketing_copy = service.generate_xiaohongshu_copy(episode_id)

        # 保存到数据库
        angle_tags_map = {
            "xhs": "AI干货向",
            "default": "轻松有趣向"
        }
        angle_tag = angle_tags_map.get(request.platform, "AI干货向")

        post = service.save_marketing_copy(
            episode_id=episode_id,
            copy=marketing_copy,
            platform=request.platform,
            angle_tag=angle_tag
        )

        return MarketingPostListResponse(
            episode_id=episode_id,
            total=1,
            items=[post],
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate marketing posts: {str(e)}"
        )


@router.get("/marketing-posts/{post_id}", response_model=MarketingPostResponse)
async def get_marketing_post(
    post_id: int,
    db: Session = Depends(get_session),
):
    """
    获取单条营销文案详情
    """
    post = db.get(MarketingPost, post_id)
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Marketing post not found: id={post_id}"
        )

    return post
