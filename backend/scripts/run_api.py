"""
API Server Launcher

启动 EnglishPod3 Enhanced REST API 服务。

Usage:
    python -m scripts.run_api
"""
import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

import uvicorn
from app.config import API_HOST, API_PORT, APP_NAME, APP_VERSION


def main():
    """启动 API 服务"""
    print(f"""
╔════════════════════════════════════════════════════════════╗
║                                                            ║
║           {APP_NAME} REST API v{APP_VERSION}                       ║
║                                                            ║
║           Starting server...                                ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝

Server:   http://{API_HOST}:{API_PORT}
Docs:     http://{API_HOST}:{API_PORT}/docs
ReDoc:    http://{API_HOST}:{API_PORT}/redoc

Press Ctrl+C to stop the server.
    """)

    uvicorn.run(
        "app.main:app",
        host=API_HOST,
        port=API_PORT,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
