"""
使用 LangChain 测试 Provider 结构化输出适配器

测试目标：
1. 验证 LangChain 的 ChatOpenAI (Kimi/Zhipu) 是否支持 json_mode
2. 验证 Pydantic 与 LangChain 的集成
3. 测试适配器模式为后续开发做准备
"""
import sys
import io
from pathlib import Path
from typing import List

# 添加 backend 目录到 Python 路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# 处理 Windows emoji 输出问题
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 检查依赖
try:
    from pydantic import BaseModel, Field, field_validator, ValidationError
    print("Pydantic 已安装")
except ImportError:
    print("错误: 需要安装 pydantic")
    sys.exit(1)

try:
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import SystemMessage, HumanMessage
    print("langchain-openai 已安装")
except ImportError:
    print("错误: 需要安装 langchain-openai")
    sys.exit(1)

from app.config import (
    MOONSHOT_API_KEY, MOONSHOT_BASE_URL, MOONSHOT_MODEL,
    ZHIPU_API_KEY, ZHIPU_BASE_URL, ZHIPU_MODEL,
    GEMINI_API_KEY, GEMINI_MODEL
)


# ==================== 测试用的 Pydantic 模型 ====================
class CorrectionSuggestion(BaseModel):
    """单条校对建议"""
    cue_id: int = Field(..., description="字幕ID", ge=1)
    original_text: str = Field(..., min_length=1, max_length=500)
    corrected_text: str = Field(..., min_length=1, max_length=500)
    reason: str = Field(..., min_length=1, max_length=200)
    confidence: float = Field(..., ge=0.0, le=1.0)


class ProofreadingResponse(BaseModel):
    """校对响应根模型"""
    corrections: List[CorrectionSuggestion] = Field(default_factory=list)


# ==================== Provider 适配器 (简化版) ====================
class ProviderAdapter:
    """Provider 适配器基类"""

    def __init__(self, provider: str, model: str, api_key: str, base_url: str = None):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.base_url = base_url

    def get_structured_llm(self, schema: type[BaseModel]):
        """获取支持结构化输出的 LLM"""
        raise NotImplementedError


class JsonModeProviderAdapter(ProviderAdapter):
    """JSON Mode Provider 适配器 (Kimi, Zhipu)"""

    def __init__(self, provider: str, model: str, api_key: str, base_url: str):
        super().__init__(provider, model, api_key, base_url)
        self.client = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=0.7
        )

    def get_structured_llm(self, schema: type[BaseModel]):
        """
        获取支持结构化输出的 LLM

        注意：Kimi 和 Zhipu 不支持 LangChain 的 with_structured_output
        需要使用 response_format={"type": "json_object"} + Pydantic 验证
        """
        class JsonModeWrapper:
            def __init__(self, client, schema):
                self.client = client
                self.schema = schema

            def invoke(self, messages, **kwargs):
                # 使用 response_format 强制 JSON 输出
                response = self.client.invoke(
                    messages,
                    response_format={"type": "json_object"},
                    **kwargs
                )

                # Pydantic 验证
                try:
                    return self.schema.model_validate_json(response.content)
                except ValidationError as e:
                    raise ValueError(
                        f"Pydantic 验证失败: {e}\n"
                        f"原始响应: {response.content[:500]}"
                    ) from e

            def bind(self, **kwargs):
                return self

        return JsonModeWrapper(self.client, schema)


class NativeProviderAdapter(ProviderAdapter):
    """原生结构化输出 Provider 适配器 (Gemini)"""

    def __init__(self, provider: str, model: str, api_key: str):
        super().__init__(provider, model, api_key, None)
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            self.client = ChatGoogleGenerativeAI(
                model=model,
                api_key=api_key,
                temperature=0.7
            )
        except ImportError:
            print("警告: langchain-google-genai 未安装")
            self.client = None

    def get_structured_llm(self, schema: type[BaseModel]):
        """
        获取支持结构化输出的 LLM

        Gemini 支持原生的 with_structured_output
        """
        if self.client is None:
            raise ValueError("Gemini 客户端未初始化")

        return self.client.with_structured_output(schema)


# ==================== 工厂函数 ====================
def get_provider_adapter(provider: str) -> ProviderAdapter:
    """Provider 工厂函数"""
    provider = provider.lower()

    if provider in ("moonshot", "kimi"):
        return JsonModeProviderAdapter(
            provider="moonshot",
            model=MOONSHOT_MODEL,
            api_key=MOONSHOT_API_KEY,
            base_url=MOONSHOT_BASE_URL
        )
    elif provider == "zhipu":
        return JsonModeProviderAdapter(
            provider="zhipu",
            model=ZHIPU_MODEL,
            api_key=ZHIPU_API_KEY,
            base_url=ZHIPU_BASE_URL
        )
    elif provider == "gemini":
        return NativeProviderAdapter(
            provider="gemini",
            model=GEMINI_MODEL,
            api_key=GEMINI_API_KEY
        )
    else:
        raise ValueError(f"不支持的 provider: {provider}")


# ==================== 测试函数 ====================
def test_provider_with_adapter(provider_name: str):
    """测试指定 provider 的适配器"""
    print("\n" + "="*60)
    print(f"测试: {provider_name.upper()} Provider Adapter")
    print("="*60)

    try:
        adapter = get_provider_adapter(provider_name)
        structured_llm = adapter.get_structured_llm(ProofreadingResponse)

        print(f"Provider: {adapter.provider}")
        print(f"Model: {adapter.model}")
        print(f"Adapter Type: {type(adapter).__name__}")

        # 测试数据
        test_cues = """请检查以下字幕中的错误：

1. Hello warld, how are you?
2. I am fine, thank you.
3. She is a good techer."""

        # 构造消息
        messages = [
            SystemMessage(content="你是字幕校对专家。请检查并返回JSON格式的修正建议。"),
            HumanMessage(content=f"""请返回以下JSON格式：
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
{test_cues}""")
        ]

        print(f"\n正在调用 {provider_name} API...")

        # 调用结构化输出
        result = structured_llm.invoke(messages)

        print(f"\n调用成功!")
        print(f"  - 返回类型: {type(result)}")
        print(f"  - corrections 数量: {len(result.corrections)}")

        for i, correction in enumerate(result.corrections, 1):
            print(f"\n  修正建议 {i}:")
            print(f"    - cue_id: {correction.cue_id}")
            print(f"    - 原文: {correction.original_text}")
            print(f"    - 修正: {correction.corrected_text}")
            print(f"    - 原因: {correction.reason}")
            print(f"    - 置信度: {correction.confidence}")

        print(f"\n{provider_name.upper()} Provider Adapter 测试通过!")
        return result

    except ValueError as e:
        print(f"\n警告: {e}")
        return None
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_adapter_error_handling():
    """测试适配器的错误处理"""
    print("\n" + "="*60)
    print("测试: 适配器错误处理")
    print("="*60)

    # 测试无效的 provider
    print("\n测试用例 1: 无效的 provider")
    try:
        adapter = get_provider_adapter("invalid_provider")
        print("  应该抛出 ValueError")
    except ValueError as e:
        print(f"  正确捕获错误: {e}")

    # 测试 Pydantic 验证失败
    print("\n测试用例 2: Pydantic 验证失败")
    if MOONSHOT_API_KEY:
        try:
            adapter = get_provider_adapter("moonshot")
            structured_llm = adapter.get_structured_llm(ProofreadingResponse)

            # 故意发送无效的消息
            messages = [
                SystemMessage(content="你是字幕校对专家。"),
                HumanMessage(content="请返回格式错误的JSON: {invalid json}")
            ]

            result = structured_llm.invoke(messages)
            print("  应该抛出 ValidationError")
        except (ValueError, ValidationError) as e:
            print(f"  正确捕获验证错误: {type(e).__name__}")


# ==================== 主函数 ====================
def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("开始测试: LangChain Provider 结构化输出适配器")
    print("="*60)

    results = {}

    # 测试各个 provider
    if MOONSHOT_API_KEY:
        results["moonshot"] = test_provider_with_adapter("moonshot")
    else:
        print("\n警告: MOONSHOT_API_KEY 未设置，跳过 Kimi 测试")

    if ZHIPU_API_KEY:
        results["zhipu"] = test_provider_with_adapter("zhipu")
    else:
        print("\n警告: ZHIPU_API_KEY 未设置，跳过 Zhipu 测试")

    if GEMINI_API_KEY:
        results["gemini"] = test_provider_with_adapter("gemini")
    else:
        print("\n警告: GEMINI_API_KEY 未设置，跳过 Gemini 测试")

    # 测试错误处理
    test_adapter_error_handling()

    # 总结
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    for provider, result in results.items():
        status = "通过" if result else "失败"
        print(f"{provider.upper()} 测试: {status}")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
