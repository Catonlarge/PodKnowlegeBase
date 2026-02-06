"""
FastAPI Main Entry

EnglishPod3 Enhanced - AI 驱动的英语学习内容自动化工作流 API 服务。
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.config import APP_NAME, APP_VERSION, API_HOST, API_PORT, CORS_ORIGINS


# ==================== Create FastAPI App ====================
app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="""
    EnglishPod3 Enhanced API

    AI 驱动的英语学习内容自动化工作流系统。

    ## 主要功能
    * **Episode 管理**: 创建、查询、更新 Episode
    * **工作流触发**: 自动化处理音频内容（下载、转录、翻译、生成文档）
    * **字幕查询**: 获取中英对照字幕
    * **翻译修正**: 支持手动修正翻译
    * **章节查询**: 获取 AI 语义分章结果
    * **营销文案**: 生成多角度营销文案
    * **内容发布**: 分发到多平台（Notion、飞书等）
    """,
    docs_url="/docs",
    redoc_url="/redoc",
    contact={
        "name": "EnglishPod3 Enhanced",
    },
) 


# ==================== Configure CORS ====================
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if CORS_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== Import and Register Routers ====================
from app.api import episodes, transcripts, translations, chapters, marketing, publications

app.include_router(episodes.router, prefix="/api/v1", tags=["episodes"])
app.include_router(transcripts.router, prefix="/api/v1", tags=["transcripts"])
app.include_router(translations.router, prefix="/api/v1", tags=["translations"])
app.include_router(chapters.router, prefix="/api/v1", tags=["chapters"])
app.include_router(marketing.router, prefix="/api/v1", tags=["marketing"])
app.include_router(publications.router, prefix="/api/v1", tags=["publications"])


# ==================== Root Endpoint ====================
@app.get("/", tags=["Root"])
async def root():
    """API 服务根路径"""
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "status": "running",
        "docs": "/docs",
        "redoc": "/redoc",
    }


# ==================== Health Check ====================
@app.get("/health", tags=["Root"])
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "service": APP_NAME,
        "version": APP_VERSION,
    }


# ==================== Global Exception Handlers ====================
@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request, exc):
    """数据库异常处理"""
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Database error occurred",
            "error_type": "database_error",
            "message": str(exc) if app.debug else "Internal database error",
        },
    )


@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    """值错误处理（如资源不存在）"""
    return JSONResponse(
        status_code=400,
        content={
            "detail": str(exc),
            "error_type": "value_error",
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """通用异常处理"""
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error_type": "internal_error",
            "message": str(exc) if app.debug else "An unexpected error occurred",
        },
    )


# ==================== Startup Event ====================
@app.on_event("startup")
async def startup_event():
    """应用启动时执行"""
    print(f"""
╔════════════════════════════════════════════════════════════╗
║                                                            ║
║     {APP_NAME} API v{APP_VERSION}                                 ║
║                                                            ║
║     Server: http://{API_HOST}:{API_PORT}                    ║
║     Docs:   /docs                                           ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
    """)


# ==================== Run Server (Development) ====================
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=API_HOST,
        port=API_PORT,
        reload=True,
        log_level="info",
    )
