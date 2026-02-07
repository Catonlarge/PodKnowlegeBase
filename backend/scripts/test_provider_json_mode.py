"""
小样本测试：验证 Kimi 和 Zhipu 的 json_mode 结构化输出

测试目标：
1. 验证 Kimi 的 response_format={"type": "json_object"} 是否工作正常
2. 验证 Zhipu 的 response_format={"type": "json_object"} 是否工作正常
3. 验证 Pydantic 验证是否能正确解析和验证AI返回的JSON
"""
import sys
import io
import json
from pathlib import Path
from typing import List

# 添加 backend 目录到 Python 路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# 处理 Windows emoji 输出问题
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 检查 pydantic 是否已安装
try:
    from pydantic import BaseModel, Field, field_validator, ValidationError
    print("Pydantic 已安装")
except ImportError:
    print("错误: 需要安装 pydantic，请运行: pip install pydantic>=2.0.0")
    sys.exit(1)

# 使用 OpenAI SDK（现有项目使用的）
try:
    from openai import OpenAI
    print("openai SDK 已安装")
except ImportError:
    print("错误: 需要安装 openai，请运行: pip install openai>=1.0.0")
    sys.exit(1)

from app.config import (
    MOONSHOT_API_KEY, MOONSHOT_BASE_URL, MOONSHOT_MODEL,
    ZHIPU_API_KEY, ZHIPU_BASE_URL, ZHIPU_MODEL
)


# ==================== 测试用的 Pydantic 模型 ====================
class CorrectionSuggestion(BaseModel):
    """单条校对建议 - 简化版用于测试"""
    cue_id: int = Field(..., description="字幕ID", ge=1)
    original_text: str = Field(..., min_length=1, max_length=500)
    corrected_text: str = Field(..., min_length=1, max_length=500)
    reason: str = Field(..., min_length=1, max_length=200)
    confidence: float = Field(..., ge=0.0, le=1.0)


class ProofreadingResponse(BaseModel):
    """校对响应根模型 - 简化版用于测试"""
    corrections: List[CorrectionSuggestion] = Field(default_factory=list)

    @field_validator('corrections')
    @classmethod
    def validate_unique_cue_ids(cls, v):
        cue_ids = [c.cue_id for c in v]
        if len(cue_ids) != len(set(cue_ids)):
            raise ValueError('存在重复的cue_id')
        return v


# ==================== 测试函数 ====================
def test_kimi_json_mode():
    """测试 Kimi 的 json_mode 结构化输出"""
    print("\n" + "="*60)
    print("测试 1: Kimi (Moonshot) JSON Mode")
    print("="*60)

    # 检查 API Key
    if not MOONSHOT_API_KEY:
        print("警告: MOONSHOT_API_KEY 未设置，跳过 Kimi 测试")
        return None

    print(f"API Key: {'*** ' + MOONSHOT_API_KEY[:10] + ' ...' if MOONSHOT_API_KEY else 'NOT SET'}")
    print(f"Base URL: {MOONSHOT_BASE_URL}")
    print(f"Model: {MOONSHOT_MODEL}")

    # 创建 Kimi OpenAI 客户端
    client = OpenAI(
        api_key=MOONSHOT_API_KEY,
        base_url=MOONSHOT_BASE_URL
    )

    # 测试数据
    test_cues = """请检查以下字幕中的错误：

1. Hello warld, how are you?
2. I am fine, thank you.
3. She is a good techer."""

    # 构造消息
    messages = [
        {"role": "system", "content": "你是字幕校对专家。请检查并返回JSON格式的修正建议。"},
        {"role": "user", "content": f"""请返回以下JSON格式：
{{
  "corrections": [
    {{
      "cue_id": 1,
      "original_text": "原文",
      "corrected_text": "修正后",
      "reason": "修正原因",
      "confidence": 0.95
    }}
  ]
}}

测试字幕：
{test_cues}"""}
    ]

    print("\n正在调用 Kimi API...")
    try:
        # 使用 response_format 强制 JSON 输出
        response = client.chat.completions.create(
            model=MOONSHOT_MODEL,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.7
        )

        response_content = response.choices[0].message.content
        print(f"响应内容类型: {type(response_content)}")
        print(f"响应内容长度: {len(response_content)} 字符")
        print(f"响应内容预览: {response_content[:200]}...")

        # 解析 JSON
        response_json = json.loads(response_content)
        print(f"\nJSON 解析成功:")
        print(f"  - corrections 数量: {len(response_json.get('corrections', []))}")

        # Pydantic 验证
        print("\n正在使用 Pydantic 验证...")
        validated_response = ProofreadingResponse.model_validate_json(response_content)
        print(f"Pydantic 验证成功!")
        print(f"  - 验证后的 corrections 数量: {len(validated_response.corrections)}")

        for i, correction in enumerate(validated_response.corrections, 1):
            print(f"\n  修正建议 {i}:")
            print(f"    - cue_id: {correction.cue_id}")
            print(f"    - 原文: {correction.original_text}")
            print(f"    - 修正: {correction.corrected_text}")
            print(f"    - 原因: {correction.reason}")
            print(f"    - 置信度: {correction.confidence}")

        print("\nKimi JSON Mode 测试通过!")
        return validated_response

    except json.JSONDecodeError as e:
        print(f"\n错误: JSON 解析失败: {e}")
        print(f"原始响应: {response_content}")
        return None
    except ValidationError as e:
        print(f"\n错误: Pydantic 验证失败: {e}")
        return None
    except Exception as e:
        print(f"\n错误: API 调用失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_zhipu_json_mode():
    """测试 Zhipu 的 json_mode 结构化输出"""
    print("\n" + "="*60)
    print("测试 2: Zhipu (GLM) JSON Mode")
    print("="*60)

    # 检查 API Key
    if not ZHIPU_API_KEY:
        print("警告: ZHIPU_API_KEY 未设置，跳过 Zhipu 测试")
        return None

    print(f"API Key: {'*** ' + ZHIPU_API_KEY[:10] + ' ...' if ZHIPU_API_KEY else 'NOT SET'}")
    print(f"Base URL: {ZHIPU_BASE_URL}")
    print(f"Model: {ZHIPU_MODEL}")

    # 创建 Zhipu OpenAI 客户端
    client = OpenAI(
        api_key=ZHIPU_API_KEY,
        base_url=ZHIPU_BASE_URL
    )

    # 测试数据
    test_cues = """请检查以下字幕中的错误：

1. Hello warld, how are you?
2. I am fine, thank you.
3. She is a good techer."""

    # 构造消息
    messages = [
        {"role": "system", "content": "你是字幕校对专家。请检查并返回JSON格式的修正建议。"},
        {"role": "user", "content": f"""请返回以下JSON格式：
{{
  "corrections": [
    {{
      "cue_id": 1,
      "original_text": "原文",
      "corrected_text": "修正后",
      "reason": "修正原因",
      "confidence": 0.95
    }}
  ]
}}

测试字幕：
{test_cues}"""}
    ]

    print("\n正在调用 Zhipu API...")
    try:
        # 使用 response_format 强制 JSON 输出
        response = client.chat.completions.create(
            model=ZHIPU_MODEL,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.7
        )

        response_content = response.choices[0].message.content
        print(f"响应内容类型: {type(response_content)}")
        print(f"响应内容长度: {len(response_content)} 字符")
        print(f"响应内容预览: {response_content[:200]}...")

        # 解析 JSON
        response_json = json.loads(response_content)
        print(f"\nJSON 解析成功:")
        print(f"  - corrections 数量: {len(response_json.get('corrections', []))}")

        # Pydantic 验证
        print("\n正在使用 Pydantic 验证...")
        validated_response = ProofreadingResponse.model_validate_json(response_content)
        print(f"Pydantic 验证成功!")
        print(f"  - 验证后的 corrections 数量: {len(validated_response.corrections)}")

        for i, correction in enumerate(validated_response.corrections, 1):
            print(f"\n  修正建议 {i}:")
            print(f"    - cue_id: {correction.cue_id}")
            print(f"    - 原文: {correction.original_text}")
            print(f"    - 修正: {correction.corrected_text}")
            print(f"    - 原因: {correction.reason}")
            print(f"    - 置信度: {correction.confidence}")

        print("\nZhipu JSON Mode 测试通过!")
        return validated_response

    except json.JSONDecodeError as e:
        print(f"\n错误: JSON 解析失败: {e}")
        print(f"原始响应: {response_content}")
        return None
    except ValidationError as e:
        print(f"\n错误: Pydantic 验证失败: {e}")
        return None
    except Exception as e:
        print(f"\n错误: API 调用失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_pydantic_validation_edge_cases():
    """测试 Pydantic 验证的边界情况"""
    print("\n" + "="*60)
    print("测试 3: Pydantic 验证边界情况")
    print("="*60)

    # 测试用例 1: 有效的 JSON
    print("\n测试用例 1: 有效的 JSON")
    valid_json = '{"corrections": [{"cue_id": 1, "original_text": "Hello warld", "corrected_text": "Hello world", "reason": "拼写错误", "confidence": 0.95}]}'
    try:
        validated = ProofreadingResponse.model_validate_json(valid_json)
        print(f"  验证通过: {len(validated.corrections)} 条修正建议")
    except ValidationError as e:
        print(f"  验证失败: {e}")

    # 测试用例 2: 缺少必填字段
    print("\n测试用例 2: 缺少必填字段 (confidence)")
    missing_field_json = '{"corrections": [{"cue_id": 1, "original_text": "Hello warld", "corrected_text": "Hello world", "reason": "拼写错误"}]}'
    try:
        validated = ProofreadingResponse.model_validate_json(missing_field_json)
        print(f"  验证通过: {len(validated.corrections)} 条修正建议")
    except ValidationError as e:
        print(f"  验证失败 (预期): 缺少必填字段")

    # 测试用例 3: 置信度超出范围
    print("\n测试用例 3: 置信度超出范围 (confidence = 1.5)")
    out_of_range_json = '{"corrections": [{"cue_id": 1, "original_text": "Hello warld", "corrected_text": "Hello world", "reason": "拼写错误", "confidence": 1.5}]}'
    try:
        validated = ProofreadingResponse.model_validate_json(out_of_range_json)
        print(f"  验证通过: {len(validated.corrections)} 条修正建议")
    except ValidationError as e:
        print(f"  验证失败 (预期): 置信度超出范围")

    # 测试用例 4: 重复的 cue_id
    print("\n测试用例 4: 重复的 cue_id")
    duplicate_id_json = '{"corrections": [{"cue_id": 1, "original_text": "Hello warld", "corrected_text": "Hello world", "reason": "拼写错误", "confidence": 0.95}, {"cue_id": 1, "original_text": "Good techer", "corrected_text": "Good teacher", "reason": "拼写错误", "confidence": 0.9}]}'
    try:
        validated = ProofreadingResponse.model_validate_json(duplicate_id_json)
        print(f"  验证通过: {len(validated.corrections)} 条修正建议")
    except ValidationError as e:
        print(f"  验证失败 (预期): 存在重复的cue_id")

    print("\nPydantic 边界测试完成!")


# ==================== 主函数 ====================
def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("开始测试: Provider JSON Mode 结构化输出")
    print("="*60)

    # 运行测试
    kimi_result = test_kimi_json_mode()
    zhipu_result = test_zhipu_json_mode()
    test_pydantic_validation_edge_cases()

    # 总结
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    print(f"Kimi 测试: {'通过' if kimi_result else '失败/跳过'}")
    print(f"Zhipu 测试: {'通过' if zhipu_result else '失败/跳过'}")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
