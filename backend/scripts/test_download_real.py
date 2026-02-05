r"""
测试 DownloadService 实际下载功能

使用方法：
1. 激活虚拟环境: D:\programming_enviroment\EnglishPod-knowledgeBase\backend\venv-kb\Scripts\Activate.ps1
2. 运行脚本: python scripts/test_download_real.py
"""
import os
import sys
from pathlib import Path

# 设置临时环境变量（仅用于测试下载功能，不需要 WhisperX）
os.environ.setdefault("HF_TOKEN", "dummy_token_for_download_test")
os.environ.setdefault("GEMINI_API_KEY", "dummy_key")
os.environ.setdefault("MOONSHOT_API_KEY", "dummy_key")
os.environ.setdefault("ZHIPU_API_KEY", "dummy_key")

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import get_session
from app.services.download_service import DownloadService


def main():
    # 测试 URL
    test_url = "https://www.youtube.com/watch?v=1em64iUFt3U"

    print(f"正在测试下载服务...")
    print(f"URL: {test_url}")
    print("-" * 60)

    # 使用上下文管理器创建数据库会话
    with get_session() as db:
        try:
            # 创建下载服务
            service = DownloadService(db)

            # 检查 yt-dlp 是否可用
            from app.services.download_service import YOUTUBE_DL_AVAILABLE
            if not YOUTUBE_DL_AVAILABLE:
                print("错误: yt-dlp 未安装")
                print("请运行: pip install yt-dlp")
                return

            print("yt-dlp 已就绪")

            # 下载并创建 Episode
            print("\n开始下载...")
            episode = service.download_with_metadata(test_url)

            # 显示结果
            print("\n" + "=" * 60)
            print("下载成功!")
            print("=" * 60)
            print(f"Episode ID   : {episode.id}")
            print(f"标题         : {episode.title}")
            print(f"时长         : {episode.duration} 秒")
            print(f"文件哈希     : {episode.file_hash}")
            print(f"音频路径     : {episode.audio_path}")
            print(f"工作流状态   : {episode.workflow_status} (DOWNLOADED)")

            # 验证文件存在
            if Path(episode.audio_path).exists():
                file_size = Path(episode.audio_path).stat().st_size
                print(f"文件大小     : {file_size / 1024 / 1024:.2f} MB")
            else:
                print("警告: 音频文件不存在")

            print("\n数据库记录已创建，可以继续进行转录处理。")

        except Exception as e:
            print(f"\n下载失败: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
