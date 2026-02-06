r"""
使用真实英文文本测试 SegmentationService

使用方法：
1. 激活虚拟环境: D:\programming_enviroment\EnglishPod-knowledgeBase\backend\venv-kb\Scripts\Activate.ps1
2. 设置环境变量: $env:MOONSHOT_API_KEY="your_api_key"
3. 运行脚本: python scripts/test_segmentation_with_file.py "path/to/english_transcript.txt"

说明：
- 此脚本读取英文文本文件并创建模拟数据进行章节切分测试
- 文本会被均匀分割成句子并模拟时间戳
"""
import os
import sys
import re
from pathlib import Path
from unittest.mock import Mock

# 设置临时环境变量（用于测试章节切分，不需要 WhisperX 和 AI API）
os.environ.setdefault("HF_TOKEN", "dummy_token_for_segmentation_test")
os.environ.setdefault("MOONSHOT_API_KEY", "dummy_key")
os.environ.setdefault("GEMINI_API_KEY", "dummy_key")
os.environ.setdefault("ZHIPU_API_KEY", "dummy_key")

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import get_session
from app.services.segmentation_service import SegmentationService
from app.services.obsidian_service import ObsidianService
from app.services.ai.ai_service import AIService
from app.models import Episode, AudioSegment, TranscriptCue, Chapter
from app.enums.workflow_status import WorkflowStatus
from app.config import OBSIDIAN_VAULT_PATH


def create_mock_ai_service():
    """创建返回模拟章节数据的 Mock AI 服务"""
    mock_ai = Mock()
    mock_ai.provider = "mock"

    def mock_query_side_effect(prompt):
        """根据提示词长度返回模拟章节"""
        # 分析提示词获取时长信息
        import re
        duration_match = re.search(r'总时长：([\d.]+)分钟', prompt)
        if duration_match:
            duration_minutes = float(duration_match.group(1))
            total_seconds = int(duration_minutes * 60)
        else:
            total_seconds = 600

        # 生成 3-5 个章节
        num_chapters = min(5, max(3, total_seconds // 180))

        chapters = []
        chapter_duration = total_seconds / num_chapters

        chapter_titles = [
            "开场介绍", "核心概念解析", "实践案例分析", "深度讨论", "总结与展望"
        ]

        for i in range(num_chapters):
            start = int(i * chapter_duration)
            end = int((i + 1) * chapter_duration) if i < num_chapters - 1 else total_seconds

            chapters.append({
                "title": chapter_titles[i] if i < len(chapter_titles) else f"第{i+1}部分",
                "summary": f"这是第{i+1}章节的中文摘要，涵盖了从{start}秒到{end}秒的内容要点。",
                "start_time": float(start),
                "end_time": float(end)
            })

        return {"chapters": chapters}

    mock_ai.query = Mock(side_effect=mock_query_side_effect)
    return mock_ai


def split_text_into_sentences(text: str) -> list:
    """
    将文本分割成句子

    Args:
        text: 原始文本

    Returns:
        list: 句子列表
    """
    # 按句子边界分割：. ! ? 以及换行
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])|[\n]+', text)
    # 过滤空句子
    sentences = [s.strip() for s in sentences if s.strip()]
    return sentences


def parse_srt_file(file_path: str) -> list:
    """
    解析 SRT 字幕文件

    Args:
        file_path: SRT 文件路径

    Returns:
        List[dict]: [{"start_time": float, "end_time": float, "speaker": str, "text": str}]
    """
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # SRT 格式：序号 -> 时间戳 -> 文本 -> 空行
    pattern = r"(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\n|\n*$)"
    matches = re.findall(pattern, content, re.DOTALL)

    def time_to_seconds(time_str: str) -> float:
        """将 SRT 时间戳转换为秒"""
        h, m, s_ms = time_str.split(":")
        s, ms = s_ms.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

    cues = []
    for match in matches:
        start_time = time_to_seconds(match[1])
        end_time = time_to_seconds(match[2])
        text = match[3].strip()

        # 提取 speaker (如果有)
        speaker = "Unknown"
        if text.startswith("["):
            match_speaker = re.match(r"\[(.*?)\]", text)
            if match_speaker:
                speaker = match_speaker.group(1)
                text = re.sub(r"\[.*?\]\s*", "", text)

        cues.append({
            "start_time": start_time,
            "end_time": end_time,
            "speaker": speaker,
            "text": text
        })

    return cues


def create_episode_from_text(db, text: str, title: str = "AI Product Transcript"):
    """
    从英文文本创建 Episode 和 TranscriptCue

    Args:
        db: 数据库会话
        text: 英文转录文本
        title: Episode 标题

    Returns:
        Episode: 创建的 Episode 对象
    """
    # 分割句子
    sentences = split_text_into_sentences(text)

    # 估算时长：假设平均每句话 5 秒
    total_duration = len(sentences) * 5

    # 创建 Episode
    episode = Episode(
        title=title,
        file_hash=f"test_{hash(text) % 1000000}",
        duration=float(total_duration),
        workflow_status=WorkflowStatus.TRANSCRIBED.value
    )
    db.add(episode)
    db.flush()

    # 创建 AudioSegment
    segment = AudioSegment(
        episode_id=episode.id,
        segment_index=0,
        segment_id="segment_001",
        start_time=0.0,
        end_time=float(total_duration),
        status="completed"
    )
    db.add(segment)
    db.flush()

    # 创建 TranscriptCue
    current_time = 0.0
    for i, sentence in enumerate(sentences):
        # 估算句子时长：每字符约 0.05 秒
        sentence_duration = max(3.0, len(sentence) * 0.05)

        # 每句话不超过 15 秒
        if sentence_duration > 15:
            sentence_duration = 15.0

        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=current_time,
            end_time=current_time + sentence_duration,
            speaker="SPEAKER_00" if i % 2 == 0 else "SPEAKER_01",
            text=sentence[:500]  # 限制长度
        )
        db.add(cue)
        current_time += sentence_duration

    db.flush()

    # 更新 Episode 时长
    episode.duration = current_time
    db.flush()

    print(f"创建 Episode: {title}")
    print(f"  句子数量: {len(sentences)}")
    print(f"  估算时长: {current_time:.0f} 秒 ({current_time/60:.1f} 分钟)")

    return episode


def create_episode_from_srt(db, srt_path: str, title: str = "SRT Transcript"):
    """
    从 SRT 文件创建 Episode 和 TranscriptCue

    Args:
        db: 数据库会话
        srt_path: SRT 文件路径
        title: Episode 标题

    Returns:
        Episode: 创建的 Episode 对象
    """
    # 解析 SRT
    cues_data = parse_srt_file(srt_path)

    if not cues_data:
        raise ValueError(f"SRT 文件解析失败或为空: {srt_path}")

    # 计算总时长
    total_duration = cues_data[-1]["end_time"]

    # 创建 Episode
    episode = Episode(
        title=title,
        file_hash=f"srt_{hash(str(total_duration)) % 1000000}",
        duration=float(total_duration),
        workflow_status=WorkflowStatus.TRANSCRIBED.value
    )
    db.add(episode)
    db.flush()

    # 创建 AudioSegment
    segment = AudioSegment(
        episode_id=episode.id,
        segment_index=0,
        segment_id="segment_001",
        start_time=0.0,
        end_time=float(total_duration),
        status="completed"
    )
    db.add(segment)
    db.flush()

    # 创建 TranscriptCue
    for cue_data in cues_data:
        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=float(cue_data["start_time"]),
            end_time=float(cue_data["end_time"]),
            speaker=cue_data["speaker"],
            text=cue_data["text"][:500]  # 限制长度
        )
        db.add(cue)

    db.flush()

    print(f"从 SRT 创建 Episode: {title}")
    print(f"  字幕数量: {len(cues_data)}")
    print(f"  实际时长: {total_duration:.0f} 秒 ({total_duration/60:.1f} 分钟)")

    return episode


def main():
    if len(sys.argv) < 2:
        print("使用方法: python scripts/test_segmentation_with_file.py <文件路径>")
        print("支持格式: .txt (纯文本) 或 .srt (字幕文件)")
        print("\n默认使用测试文件...")
        text_file = Path(r"D:\programming_enviroment\learning-EnglishPod3\docs\018_analysis\018_fulltext.txt")
    else:
        text_file = Path(sys.argv[1])

    if not text_file.exists():
        print(f"错误: 文件不存在: {text_file}")
        return

    print("=" * 70)
    print("章节切分测试 (新版 Prompt)")
    print("=" * 70)
    print(f"文件路径: {text_file}")
    print(f"文件大小: {text_file.stat().st_size / 1024:.1f} KB")
    print(f"文件格式: {text_file.suffix.upper()}")
    print()

    # 强制使用 Mock 模式进行测试
    # 如需真实 AI 切分，将下面的 FORCE_USE_MOCK 改为 False
    FORCE_USE_MOCK = False

    if FORCE_USE_MOCK:
        print("\n使用 Mock 模式（模拟 AI 章节切分响应）")
        print("如需真实 AI 切分，将脚本中的 FORCE_USE_MOCK 改为 False\n")
    else:
        print(f"\n使用真实 AI 服务: Moonshot")
        print("新版 Prompt 特性:")
        print("  - 短内容(<8分钟): 1-3 章，甚至不划分")
        print("  - 拒绝机械式切分，保持语义完整")
        print()

    # 创建数据库会话
    with get_session() as db:
        try:
            # 创建 AI 服务
            if FORCE_USE_MOCK:
                ai_service = create_mock_ai_service()
                print(f"AI 服务提供商: {ai_service.provider} (Mock)")
            else:
                ai_service = AIService(provider="moonshot")
                print(f"AI 服务提供商: {ai_service.provider}")
            print()

            # 根据文件类型创建 Episode
            print("-" * 70)
            if text_file.suffix.lower() == ".srt":
                # SRT 文件
                episode = create_episode_from_srt(
                    db,
                    str(text_file),
                    title=f"SRT: {text_file.stem}"
                )
            else:
                # 纯文本文件
                print("读取文件内容...")
                with open(text_file, 'r', encoding='utf-8') as f:
                    text_content = f.read()

                # 限制内容长度（避免太长）
                max_chars = 15000  # 约 15 分钟的播客内容
                if len(text_content) > max_chars:
                    print(f"文件过长 ({len(text_content)} 字符)，截取前 {max_chars} 字符")
                    text_content = text_content[:max_chars]

                episode = create_episode_from_text(
                    db,
                    text_content,
                    title=f"Transcript: {text_file.stem}"
                )
            print("-" * 70)

            # 创建章节切分服务
            print("\n开始章节切分...")
            print("-" * 70)
            service = SegmentationService(db, ai_service)

            # 执行章节切分
            chapters = service.analyze_and_segment(episode.id)

            # 显示结果
            print("\n" + "=" * 70)
            print("章节切分完成!")
            print("=" * 70)
            print(f"章节数量: {len(chapters)}")
            print()

            for i, chapter in enumerate(chapters, 1):
                minutes = int(chapter.start_time // 60)
                seconds = int(chapter.start_time % 60)
                end_minutes = int(chapter.end_time // 60)
                end_seconds = int(chapter.end_time % 60)

                print(f"章节 {i}: {chapter.title}")
                print(f"  时间: [{minutes:02d}:{seconds:02d}] - [{end_minutes:02d}:{end_seconds:02d}]")
                print(f"  摘要: {chapter.summary}")
                print()

            # 验证 Episode 状态更新
            db.refresh(episode)
            print(f"Episode 工作流状态: {WorkflowStatus(episode.workflow_status).label}")

            # 显示关联的 TranscriptCue 数量
            from sqlalchemy import func
            cue_counts = db.query(
                Chapter.id,
                Chapter.title,
                func.count(TranscriptCue.id).label('cue_count')
            ).outerjoin(
                TranscriptCue, TranscriptCue.chapter_id == Chapter.id
            ).filter(
                Chapter.episode_id == episode.id
            ).group_by(Chapter.id).all()

            print("\n章节关联统计:")
            print("-" * 70)
            total_cues = 0
            for chapter_id, title, cue_count in cue_counts:
                print(f"  {title}: {cue_count} 条")
                total_cues += cue_count
            print(f"  总计: {total_cues} 条 TranscriptCue")

            # 输出到 Obsidian
            print("\n" + "=" * 70)
            print("输出到 Obsidian...")
            print("=" * 70)
            print(f"Obsidian Vault: {OBSIDIAN_VAULT_PATH}")

            obsidian_service = ObsidianService(db)
            file_path = obsidian_service.save_episode(episode.id, language_code="zh")

            print(f"\n[OK] Obsidian 文档已生成:")
            print(f"   路径: {file_path}")
            print(f"   文件名: {file_path.name}")

            print("\n" + "=" * 70)
            print("测试成功完成!")
            print("=" * 70)

        except Exception as e:
            print(f"\n测试失败: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
