#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
营销文案 LLM 调用诊断脚本

用于排查为何营销文案一直走兜底：检查 StructuredLLM 初始化、字幕长度、实际调用异常。
用法: python scripts/debug_marketing_llm.py [episode_id]
"""
import io
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.database import get_session
from app.config import (
    get_marketing_llm_config,
    MARKETING_LLM_PROVIDER,
    ZHIPU_API_KEY,
    MOONSHOT_API_KEY,
    GEMINI_API_KEY,
)
from app.services.marketing_service import MarketingService
from app.models import TranscriptCue, AudioSegment


def main():
    episode_id = int(sys.argv[1]) if len(sys.argv) > 1 else 21

    print("=" * 60)
    print("营销文案 LLM 诊断")
    print("=" * 60)

    # 1. 检查配置
    print("\n[1] 配置检查")
    print(f"  MARKETING_LLM_PROVIDER (config): {MARKETING_LLM_PROVIDER}")
    try:
        cfg = get_marketing_llm_config()
        print(f"  provider: {cfg.get('provider')}")
        print(f"  model: {cfg.get('model')}")
        api_key = cfg.get("api_key")
        key_preview = f"{api_key[:8]}...{api_key[-4:]}" if api_key and len(api_key) > 12 else "(空或过短)"
        print(f"  api_key: {key_preview}")
    except Exception as e:
        print(f"  [ERROR] get_marketing_llm_config: {e}")
        return 1

    # 2. 检查环境变量
    print("\n[2] 环境变量")
    import os
    for name in ["ZHIPU_API_KEY", "MOONSHOT_API_KEY", "GEMINI_API_KEY"]:
        val = os.environ.get(name, "")
        status = "OK" if val else "MISSING"
        print(f"  {name}: {status}")

    # 3. 初始化 MarketingService
    print("\n[3] MarketingService 初始化")
    with get_session() as db:
        service = MarketingService(db)
        if service.structured_llm is None:
            print("  [FAIL] structured_llm = None (初始化失败，会直接走兜底)")
        else:
            print("  [OK] structured_llm 已初始化")

        # 4. 字幕长度
        cues = (
            db.query(TranscriptCue)
            .join(AudioSegment, TranscriptCue.segment_id == AudioSegment.id)
            .filter(AudioSegment.episode_id == episode_id)
            .order_by(TranscriptCue.start_time)
            .all()
        )
        transcripts_text = service._get_full_transcripts(episode_id)
        char_count = len(transcripts_text)
        token_approx = char_count // 2  # 中文约 2 字符/token
        print(f"\n[4] 字幕统计 (episode_id={episode_id})")
        print(f"  cue 数量: {len(cues)}")
        print(f"  总字符数: {char_count}")
        print(f"  约 token 数: {token_approx}")
        if token_approx > 30000:
            print("  [WARN] 可能超出多数模型 context 限制 (8k-32k)，建议截断")

        # 5. 实际调用（捕获异常）
        if service.structured_llm:
            print("\n[5] 尝试调用 LLM (会打印真实异常)")
            try:
                copies = service.generate_xiaohongshu_copy_multi_angle(episode_id)
                print(f"  [OK] 成功，返回 {len(copies)} 个角度")
                if copies and copies[0].metadata.get("fallback"):
                    print("  [WARN] 但内容是兜底 (metadata.fallback=True)")
            except Exception as e:
                print(f"  [FAIL] 异常: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("\n[5] 跳过调用 (structured_llm 未初始化)")

    print("\n" + "=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
