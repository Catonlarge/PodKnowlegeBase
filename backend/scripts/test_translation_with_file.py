r"""
使用真实英文文本测试 TranslationService

使用方法：
1. 激活虚拟环境: D:\programming_enviroment\EnglishPod-knowledgeBase\backend\venv-kb\Scripts\Activate.ps1
2. 设置环境变量: $env:MOONSHOT_API_KEY="your_api_key"
3. 运行脚本: python scripts/test_translation_with_file.py "path/to/english_transcript.txt"

说明：
- 此脚本读取英文文本文件并创建模拟数据进行翻译测试
- 文本会被分割成句子并模拟时间戳
- 使用真实 AI 服务进行翻译
"""
import os
import sys
import re
from pathlib import Path
from unittest.mock import Mock

# 设置临时环境变量
os.environ.setdefault("HF_TOKEN", "dummy_token_for_translation_test")
os.environ.setdefault("MOONSHOT_API_KEY", "dummy_key")
os.environ.setdefault("GEMINI_API_KEY", "dummy_key")
os.environ.setdefault("ZHIPU_API_KEY", "dummy_key")

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import get_session
from app.services.translation_service import TranslationService
from app.services.ai.ai_service import AIService
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


def main():
    if len(sys.argv) < 2:
        print("使用方法: python scripts/test_translation_with_file.py <英文文本文件路径>")
        print("\n默认使用测试文件...")
        text_file = Path(r"D:\programming_enviroment\learning-EnglishPod3\docs\018_analysis\018_fulltext.txt")
    else:
        text_file = Path(sys.argv[1])

    if not text_file.exists():
        print(f"错误: 文件不存在: {text_file}")
        return

    print("=" * 70)
    print("使用真实英文文本进行翻译测试")
    print("=" * 70)
    print(f"文件路径: {text_file}")
    print(f"文件大小: {text_file.stat().st_size / 1024:.1f} KB")
    print()

    # 读取文件
    print("读取文件内容...")
    with open(text_file, 'r', encoding='utf-8') as f:
        text_content = f.read()

    # 限制内容长度（避免太长）
    max_chars = 3000  # 限制句子数量用于测试
    if len(text_content) > max_chars:
        print(f"文件过长 ({len(text_content)} 字符)，截取前 {max_chars} 字符")
        text_content = text_content[:max_chars]

    # 检查是否使用真实 AI 服务
    FORCE_USE_MOCK = False

    if FORCE_USE_MOCK:
        print("\n使用 Mock 模式（模拟 AI 翻译响应）")
        print("如需真实翻译，将脚本中的 FORCE_USE_MOCK 改为 False\n")

        # 创建 Mock AI 服务
        mock_ai = Mock()
        mock_ai.provider = "mock"

        def mock_query_side_effect(prompt):
            """返回模拟翻译"""
            # 从 prompt 中提取英文文本
            match = re.search(r'\*\*英文：\*\*\s*\n?(.+)', prompt, re.DOTALL)
            if match:
                english_text = match.group(1).strip()[:50]
                return {
                    "type": "sentence",
                    "content": {"translation": f"[模拟翻译] {english_text}..."}
                }
            return {
                "type": "sentence",
                "content": {"translation": "[模拟翻译]"}
            }

        mock_ai.query = Mock(side_effect=mock_query_side_effect)
        ai_service = mock_ai
        print(f"AI 服务提供商: {ai_service.provider} (Mock)")
    else:
        print(f"\n使用真实 AI 服务: Moonshot\n")
        ai_service = AIService(provider="moonshot")
        print(f"AI 服务提供商: {ai_service.provider}")

    # 创建数据库会话
    with get_session() as db:
        try:
            # 从文本创建 Episode
            print("-" * 70)
            episode = create_episode_from_text(
                db,
                text_content,
                title=f"Translation Test: {text_file.stem}"
            )
            print("-" * 70)

            # 创建翻译服务
            print("\n开始批量翻译...")
            print("-" * 70)
            service = TranslationService(db, ai_service)

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
