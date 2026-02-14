r"""
使用真实英文文本或 SRT 字幕测试 TranslationService

使用方法：
1. 激活虚拟环境: D:\programming_enviroment\EnglishPod-knowledgeBase\backend\venv-kb\Scripts\Activate.ps1
2. 设置环境变量: $env:MOONSHOT_API_KEY="your_api_key"
3. 运行脚本: python scripts/test_translation_with_file.py "path/to/file.txt"
   或: python scripts/test_translation_with_file.py "path/to/subtitles.srt"

说明：
- 支持 .txt（纯文本）和 .srt（字幕）格式
- 使用真实 AI 服务进行翻译
"""
import os
import sys
import re
from pathlib import Path

# 设置临时环境变量
os.environ.setdefault("HF_TOKEN", "dummy_token_for_translation_test")
os.environ.setdefault("MOONSHOT_API_KEY", "dummy_key")
os.environ.setdefault("GEMINI_API_KEY", "dummy_key")
os.environ.setdefault("ZHIPU_API_KEY", "dummy_key")

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import get_session
from app.services.translation_service import TranslationService
from app.models import Episode, AudioSegment, TranscriptCue, Translation
from app.enums.workflow_status import WorkflowStatus
from app.enums.translation_status import TranslationStatus


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


def create_episode_from_text(db, text: str, title: str = "AI Translation Test") -> Episode:
    """
    从英文文本创建 Episode 和 TranscriptCue

    Args:
        db: 数据库会话
        text: 英文文本
        title: Episode 标题

    Returns:
        Episode: 创建的 Episode 对象
    """
    # 分割句子
    sentences = split_text_into_sentences(text)

    # 估算时长：假设每句话 5 秒
    total_duration = len(sentences) * 5

    # 创建 Episode
    episode = Episode(
        title=title,
        file_hash=f"test_translation_{hash(text) % 1000000}",
        duration=float(total_duration),
        workflow_status=WorkflowStatus.SEGMENTED.value
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
        # 估算句子时长
        sentence_duration = max(3.0, min(10.0, len(sentence) * 0.08))

        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=current_time,
            end_time=current_time + sentence_duration,
            speaker="SPEAKER_00" if i % 2 == 0 else "SPEAKER_01",
            text=sentence[:500]
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


def parse_srt_file(file_path: str) -> list:
    """
    解析 SRT 字幕文件

    Returns:
        List[dict]: [{"start_time": float, "end_time": float, "speaker": str, "text": str}]
    """
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = r"(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\n|\n*$)"
    matches = re.findall(pattern, content, re.DOTALL)

    def time_to_seconds(time_str: str) -> float:
        h, m, s_ms = time_str.split(":")
        s, ms = s_ms.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

    cues = []
    for match in matches:
        start_time = time_to_seconds(match[1])
        end_time = time_to_seconds(match[2])
        text = match[3].strip()
        speaker = "Unknown"
        if text.startswith("["):
            match_speaker = re.match(r"\[(.*?)\]", text)
            if match_speaker:
                speaker = match_speaker.group(1)
                text = re.sub(r"\[.*?\]\s*", "", text)
        cues.append({"start_time": start_time, "end_time": end_time, "speaker": speaker, "text": text})
    return cues


def create_episode_from_srt(db, srt_path: str, title: str = "SRT Translation Test") -> Episode:
    """从 SRT 文件创建 Episode 和 TranscriptCue"""
    cues_data = parse_srt_file(srt_path)
    if not cues_data:
        raise ValueError(f"SRT 文件解析失败或为空: {srt_path}")

    total_duration = cues_data[-1]["end_time"]
    episode = Episode(
        title=title,
        file_hash=f"srt_{hash(str(total_duration)) % 1000000}",
        duration=float(total_duration),
        workflow_status=WorkflowStatus.SEGMENTED.value
    )
    db.add(episode)
    db.flush()

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

    for cue_data in cues_data:
        cue = TranscriptCue(
            segment_id=segment.id,
            start_time=float(cue_data["start_time"]),
            end_time=float(cue_data["end_time"]),
            speaker=cue_data["speaker"],
            text=cue_data["text"][:500]
        )
        db.add(cue)
    db.flush()

    print(f"创建 Episode: {title}")
    print(f"  Cue 数量: {len(cues_data)}")
    print(f"  时长: {total_duration:.0f} 秒 ({total_duration/60:.1f} 分钟)")
    return episode


def main():
    default_srt = Path(r"D:\programming_enviroment\learning-EnglishPod3\docs\016_analysis\016_subtitles_original.srt")
    if len(sys.argv) < 2:
        print("使用方法: python scripts/test_translation_with_file.py <文件路径>")
        print("  支持 .txt 或 .srt 格式")
        print(f"\n默认使用: {default_srt.name}")
        text_file = default_srt
    else:
        text_file = Path(sys.argv[1])

    if not text_file.exists():
        print(f"错误: 文件不存在: {text_file}")
        return

    print("=" * 70)
    print("TranslationService 翻译测试")
    print("=" * 70)
    print(f"文件路径: {text_file}")
    print(f"文件大小: {text_file.stat().st_size / 1024:.1f} KB")
    print()

    is_srt = text_file.suffix.lower() == ".srt"

    # 创建数据库会话
    with get_session() as db:
        try:
            print("-" * 70)
            if is_srt:
                episode = create_episode_from_srt(
                    db, str(text_file), title=f"Translation Test: {text_file.stem}"
                )
            else:
                print("读取文件内容...")
                with open(text_file, 'r', encoding='utf-8') as f:
                    text_content = f.read()
                max_chars = 3000
                if len(text_content) > max_chars:
                    print(f"文件过长，截取前 {max_chars} 字符")
                    text_content = text_content[:max_chars]
                episode = create_episode_from_text(
                    db, text_content, title=f"Translation Test: {text_file.stem}"
                )
            print("-" * 70)

            # 创建翻译服务（使用 Moonshot）
            print("\n开始批量翻译 (provider=moonshot)...")
            print("-" * 70)
            service = TranslationService(db, provider="moonshot")

            # 执行批量翻译
            count = service.batch_translate(episode.id, language_code="zh")

            # 显示结果
            print("\n" + "=" * 70)
            print("翻译完成!")
            print("=" * 70)
            print(f"翻译数量: {count}")

            # 显示部分翻译结果
            print("\n翻译结果示例（前 5 条）:")
            print("-" * 70)

            translations = db.query(Translation).filter(
                Translation.language_code == "zh",
                Translation.translation_status == TranslationStatus.COMPLETED.value
            ).limit(5).all()

            for t in translations:
                cue = db.query(TranscriptCue).filter(TranscriptCue.id == t.cue_id).first()
                if cue:
                    print(f"\n[Cue {t.cue_id}]")
                    print(f"  英文: {cue.text[:80]}...")
                    print(f"  中文: {t.translation}")
                    print(f"  RLHF: original={'相同' if t.original_translation == t.translation else '不同'}, is_edited={t.is_edited}")

            # 验证 Episode 状态更新
            db.refresh(episode)
            print(f"\nEpisode 工作流状态: {WorkflowStatus(episode.workflow_status).label}")

            # 统计信息
            from sqlalchemy import func
            stats = db.query(
                Translation.translation_status,
                func.count(Translation.id)
            ).filter(
                Translation.language_code == "zh"
            ).group_by(Translation.translation_status).all()

            print("\n翻译统计:")
            print("-" * 70)
            for status, count in stats:
                print(f"  {status}: {count}")

            total_translations = db.query(Translation).filter(
                Translation.language_code == "zh"
            ).count()
            print(f"  总计: {total_translations}")

            print("\n" + "=" * 70)
            print("测试成功完成!")
            print("=" * 70)

        except Exception as e:
            print(f"\n测试失败: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
