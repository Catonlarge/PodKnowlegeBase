r"""
测试 SegmentationService 实际章节切分功能

使用方法：
1. 激活虚拟环境: D:\programming_enviroment\EnglishPod-knowledgeBase\backend\venv-kb\Scripts\Activate.ps1
2. 设置环境变量: $env:MOONSHOT_API_KEY="your_api_key"
3. 运行脚本: python scripts/test_segmentation_real.py

说明：
- 此脚本会创建一个模拟的 Episode 和 TranscriptCue
- 然后调用 AI 进行语义章节切分
- 可以使用提供的示例英文文本，也可以修改为自己的文本
"""
import os
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import get_session
from app.services.segmentation_service import SegmentationService
from app.services.ai.ai_service import AIService
from app.models import Episode, AudioSegment, TranscriptCue
from app.enums.workflow_status import WorkflowStatus


# 示例英文播客转录文本（10分钟内容模拟）
SAMPLE_TRANSCRIPT = """
[00:00] SPEAKER_00: Hello everyone, and welcome back to another episode of our English learning podcast. I'm your host, and today we have an exciting topic to discuss.

[00:45] SPEAKER_00: Before we dive in, I want to thank our listeners for the overwhelming response to our previous episode about business English expressions. It's been our most downloaded episode this month!

[01:30] SPEAKER_01: That's amazing! Today we're going to talk about something different but equally important. We'll be discussing cultural differences in workplace communication.

[02:15] SPEAKER_00: Yes, exactly. Understanding these cultural nuances can make a huge difference in your professional life, especially if you work in an international environment.

[03:00] SPEAKER_01: Let's start with the concept of direct versus indirect communication. In some cultures, like the United States or Germany, people tend to be very direct.

[03:45] SPEAKER_00: Right. They say what they mean, and they mean what they say. But in many Asian cultures, communication is much more indirect. The message is often between the lines rather than explicitly stated.

[04:30] SPEAKER_01: This can lead to misunderstandings. For example, when an American manager says "this needs improvement," they're being constructive. But in some cultures, this might be seen as too harsh.

[05:15] SPEAKER_00: Another important aspect is the concept of hierarchy. In some cultures, the boss is always right, and questioning them publicly is unthinkable.

[06:00] SPEAKER_01: While in others, especially in tech companies, open discussion and disagreement are encouraged, regardless of position.

[06:45] SPEAKER_00: Time perception is another big one. Some cultures are very time-conscious, while others view time more flexibly.

[07:30] SPEAKER_01: So what's our advice for our listeners? First, observe. Pay attention to how people communicate in your workplace.

[08:15] SPEAKER_00: Second, ask questions if you're unsure. It's better to clarify than to assume. And third, be flexible and adapt to the situation.

[09:00] SPEAKER_01: That's excellent advice. Remember, there's no right or wrong way to communicate - it's about understanding and adapting.

[09:45] SPEAKER_00: Thank you for listening! Don't forget to subscribe and leave a review. See you next time!
"""


def create_test_episode_with_transcript(db, transcript_text: str = None):
    """
    创建测试用的 Episode 和 TranscriptCue

    Args:
        db: 数据库会话
        transcript_text: 转录文本（可选，默认使用示例文本）

    Returns:
        Episode: 创建的 Episode 对象
    """
    if transcript_text is None:
        transcript_text = SAMPLE_TRANSCRIPT

    # 创建 Episode
    episode = Episode(
        title="Cultural Differences in Workplace Communication",
        file_hash="test_segmentation_001",
        duration=600.0,  # 10分钟
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
        end_time=600.0,
        status="completed"
    )
    db.add(segment)
    db.flush()

    # 解析转录文本并创建 TranscriptCue
    lines = transcript_text.strip().split('\n')
    for line in lines:
        if line.strip():
            # 解析格式: [MM:SS] SPEAKER_XX: text
            if line.startswith('['):
                time_end = line.index(']')
                time_str = line[1:time_end]
                speaker_end = line.index(':', time_end)
                speaker = line[time_end + 2:speaker_end].strip()
                text = line[speaker_end + 2:].strip()

                # 解析时间
                minutes, seconds = map(int, time_str.split(':'))
                start_time = minutes * 60 + seconds

                cue = TranscriptCue(
                    segment_id=segment.id,
                    start_time=float(start_time),
                    end_time=float(start_time + 45),  # 假设每句约45秒
                    speaker=speaker,
                    text=text
                )
                db.add(cue)

    db.flush()
    print(f"创建测试 Episode: ID={episode.id}")
    print(f"创建 {len([l for l in lines if l.strip() and l.startswith('[')])} 条 TranscriptCue")

    return episode


def main():
    print("=" * 70)
    print("SegmentationService 功能测试")
    print("=" * 70)

    # 检查环境变量
    moonshot_key = os.environ.get("MOONSHOT_API_KEY")
    if not moonshot_key or moonshot_key == "your_api_key":
        print("\n警告: 未设置 MOONSHOT_API_KEY 环境变量")
        print("请使用: $env:MOONSHOT_API_KEY=\"your_api_key\"")
        print("或者此脚本将使用 Mock 模式\n")

    # 创建数据库会话
    with get_session() as db:
        try:
            # 创建 AI 服务
            ai_service = AIService(provider="moonshot")
            print(f"AI 服务提供商: {ai_service.provider}")
            if ai_service.use_mock:
                print("使用 Mock 模式（不会调用真实 API）")
            print()

            # 创建测试 Episode
            print("-" * 70)
            print("创建测试数据...")
            episode = create_test_episode_with_transcript(db)
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
                print(f"章节 {i}: {chapter.title}")
                print(f"  时间范围: {chapter.start_time:.0f}s - {chapter.end_time:.0f}s")
                print(f"  时长: {chapter.duration:.0f}秒")
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

            print("\n章节关联的 Cues 统计:")
            print("-" * 70)
            for chapter_id, title, cue_count in cue_counts:
                print(f"  {title}: {cue_count} 条")

            print("\n" + "=" * 70)
            print("测试成功完成!")
            print("=" * 70)

        except Exception as e:
            print(f"\n测试失败: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
