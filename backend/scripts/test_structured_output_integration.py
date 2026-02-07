"""
完整集成测试：AI 结构化输出系统

这个脚本测试整个 AI 结构化输出系统，包括：
1. Provider 适配器
2. StructuredLLM 包装器
3. Pydantic Schema 验证
4. 业务验证器
5. 重试装饰器
"""
import sys
import io
from pathlib import Path

# 添加 backend 目录到 Python 路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# 处理 Windows emoji 输出问题
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from langchain_core.messages import SystemMessage, HumanMessage

from app.services.ai.structured_llm import StructuredLLM
from app.services.ai.retry import ai_retry
from app.services.ai.schemas.proofreading_schema import ProofreadingResponse
from app.services.ai.schemas.segmentation_schema import SegmentationResponse
from app.services.ai.validators.proofreading_validator import ProofreadingValidator
from app.services.ai.validators.segmentation_validator import SegmentationValidator

from app.config import (
    MOONSHOT_API_KEY, MOONSHOT_BASE_URL, MOONSHOT_MODEL,
    ZHIPU_API_KEY, ZHIPU_BASE_URL, ZHIPU_MODEL,
    GEMINI_API_KEY, GEMINI_MODEL
)


# ==================== 测试函数 ====================
def test_structured_llm_with_provider(provider_name: str, api_key: str, base_url: str = None, model: str = None):
    """测试 StructuredLLM 与指定 provider 的集成"""
    print("\n" + "="*60)
    print(f"测试: {provider_name.upper()} StructuredLLM 集成")
    print("="*60)

    if not api_key:
        print(f"警告: {provider_name}_API_KEY 未设置，跳过测试")
        return None

    # 创建 StructuredLLM
    llm = StructuredLLM(
        provider=provider_name,
        model=model,
        api_key=api_key,
        base_url=base_url
    )

    print(f"Provider: {llm.provider}")
    print(f"Model: {llm.model}")
    print(f"Method: {llm.config.preferred_method}")

    # 获取结构化输出 LLM
    structured_llm = llm.with_structured_output(ProofreadingResponse)

    # 构造测试消息
    messages = [
        SystemMessage(content="你是字幕校对专家。请检查并返回JSON格式的修正建议。"),
        HumanMessage(content="""请返回以下JSON格式：
{
  "corrections": [
    {
      "cue_id": 1,
      "original_text": "原文",
      "corrected_text": "修正后",
      "reason": "修正原因",
      "confidence": 0.95
    }
  ]
}

测试字幕：
1. Hello warld, how are you?
2. I am fine, thank you.
3. She is a good techer.""")
    ]

    print(f"\n正在调用 {provider_name} API...")
    try:
        result = structured_llm.invoke(messages)

        print(f"\n调用成功!")
        print(f"  - 返回类型: {type(result).__name__}")
        print(f"  - corrections 数量: {len(result.corrections)}")

        for i, correction in enumerate(result.corrections, 1):
            print(f"\n  修正建议 {i}:")
            print(f"    - cue_id: {correction.cue_id}")
            print(f"    - 原文: {correction.original_text}")
            print(f"    - 修正: {correction.corrected_text}")
            print(f"    - 原因: {correction.reason}")
            print(f"    - 置信度: {correction.confidence}")

        print(f"\n{provider_name.upper()} StructuredLLM 集成测试通过!")
        return result

    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_business_validators():
    """测试业务验证器"""
    print("\n" + "="*60)
    print("测试: 业务验证器")
    print("="*60)

    # 测试 ProofreadingValidator
    print("\n测试用例 1: ProofreadingValidator - 有效输入")
    valid_response = ProofreadingResponse(
        corrections=[
            {
                "cue_id": 1,
                "original_text": "Hello warld",
                "corrected_text": "Hello world",
                "reason": "拼写错误",
                "confidence": 0.95
            },
            {
                "cue_id": 2,
                "original_text": "Good techer",
                "corrected_text": "Good teacher",
                "reason": "拼写错误",
                "confidence": 0.9
            }
        ]
    )

    try:
        validated = ProofreadingValidator.validate(
            valid_response,
            valid_cue_ids={1, 2, 3, 4, 5},
            total_cues=5
        )
        print(f"  校对验证通过: {len(validated.corrections)} 条修正建议")
    except ValueError as e:
        print(f"  校对验证失败: {e}")

    # 测试无效 cue_id
    print("\n测试用例 2: ProofreadingValidator - 无效 cue_id")
    invalid_response = ProofreadingResponse(
        corrections=[
            {
                "cue_id": 999,  # 不在 valid_cue_ids 中
                "original_text": "Hello warld",
                "corrected_text": "Hello world",
                "reason": "拼写错误",
                "confidence": 0.95
            }
        ]
    )

    try:
        validated = ProofreadingValidator.validate(
            invalid_response,
            valid_cue_ids={1, 2, 3, 4, 5},
            total_cues=5
        )
        print(f"  应该抛出 ValueError")
    except ValueError as e:
        print(f"  正确捕获错误: 发现无效的cue_id")

    # 测试 SegmentationValidator
    print("\n测试用例 3: SegmentationValidator - 有效输入")
    valid_segmentation = SegmentationResponse(
        chapters=[
            {
                "title": "第一章",
                "summary": "开场介绍",
                "start_time": 0.0,
                "end_time": 60.0
            },
            {
                "title": "第二章",
                "summary": "主要内容",
                "start_time": 60.0,
                "end_time": 120.0
            }
        ]
    )

    try:
        validated = SegmentationValidator.validate(
            valid_segmentation,
            total_duration=120.0
        )
        print(f"  章节验证通过: {len(validated.chapters)} 个章节")
    except ValueError as e:
        print(f"  章节验证失败: {e}")

    # 测试第一章不从 0 开始
    print("\n测试用例 4: SegmentationValidator - 第一章不从0开始")
    invalid_segmentation = SegmentationResponse(
        chapters=[
            {
                "title": "第一章",
                "summary": "开场介绍",
                "start_time": 10.0,  # 应该从 0 开始
                "end_time": 60.0
            }
        ]
    )

    try:
        validated = SegmentationValidator.validate(
            invalid_segmentation,
            total_duration=120.0
        )
        print(f"  应该抛出 ValueError")
    except ValueError as e:
        print(f"  正确捕获错误: 第一章必须从0秒开始")


def test_retry_decorator():
    """测试重试装饰器"""
    print("\n" + "="*60)
    print("测试: 重试装饰器")
    print("="*60)

    call_count = 0

    @ai_retry(max_retries=2, initial_delay=0.1)
    def failing_function():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ValueError("模拟失败")
        return "成功"

    print("\n测试用例 1: 重试后成功")
    try:
        result = failing_function()
        print(f"  结果: {result}, 调用次数: {call_count}")
    except Exception as e:
        print(f"  失败: {e}")

    # 重置计数器
    call_count = 0

    @ai_retry(max_retries=2, initial_delay=0.1)
    def always_failing_function():
        nonlocal call_count
        call_count += 1
        raise ValueError("持续失败")

    print("\n测试用例 2: 重试后仍然失败")
    try:
        result = always_failing_function()
        print(f"  应该抛出异常")
    except ValueError as e:
        print(f"  正确捕获异常: {e}, 总调用次数: {call_count}")


# ==================== 主函数 ====================
def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("AI 结构化输出系统 - 完整集成测试")
    print("="*60)

    results = {}

    # 测试各个 provider 的 StructuredLLM 集成
    if MOONSHOT_API_KEY:
        results["moonshot"] = test_structured_llm_with_provider(
            "moonshot",
            MOONSHOT_API_KEY,
            MOONSHOT_BASE_URL,
            MOONSHOT_MODEL
        )
    else:
        print("\n警告: MOONSHOT_API_KEY 未设置，跳过 Kimi 测试")

    if ZHIPU_API_KEY:
        results["zhipu"] = test_structured_llm_with_provider(
            "zhipu",
            ZHIPU_API_KEY,
            ZHIPU_BASE_URL,
            ZHIPU_MODEL
        )
    else:
        print("\n警告: ZHIPU_API_KEY 未设置，跳过 Zhipu 测试")

    if GEMINI_API_KEY:
        results["gemini"] = test_structured_llm_with_provider(
            "gemini",
            GEMINI_API_KEY,
            None,
            GEMINI_MODEL
        )
    else:
        print("\n警告: GEMINI_API_KEY 未设置，跳过 Gemini 测试")

    # 测试业务验证器
    test_business_validators()

    # 测试重试装饰器
    test_retry_decorator()

    # 总结
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    for provider, result in results.items():
        status = "通过" if result else "失败"
        print(f"{provider.upper()} StructuredLLM 测试: {status}")
    print("业务验证器测试: 完成")
    print("重试装饰器测试: 完成")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
