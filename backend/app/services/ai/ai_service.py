"""
AI 查询服务

提供统一的 AI 查询接口，支持自动判断查询类型（word/phrase/sentence）。
支持:
1. Google Gemini 原生接口
2. OpenAI 兼容接口 (Kimi/Moonshot, DeepSeek, Zhipu, GPT-4, etc.)
"""
import json
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Optional, Dict

# Google GenAI SDK
try:
    from google import genai
except ImportError:
    import google.generativeai as genai
# OpenAI SDK (通用兼容客户端)
from openai import OpenAI

# 引入统一配置
from app.config import (
    MOONSHOT_API_KEY,
    MOONSHOT_BASE_URL,
    MOONSHOT_MODEL,
    ZHIPU_API_KEY,
    ZHIPU_BASE_URL,
    ZHIPU_MODEL,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    AI_QUERY_TIMEOUT,
    USE_AI_MOCK
)

logger = logging.getLogger(__name__)

# 默认 AI 提供商（可配置为 "moonshot", "zhipu", "gemini"）
DEFAULT_AI_PROVIDER = "moonshot"


class AIService:
    """
    AI 查询服务类

    提供统一的查询接口，AI 自动判断查询类型（word/phrase/sentence）。
    支持多个 AI 提供商，通过 provider 参数选择。
    """

    def __init__(self, provider: str = DEFAULT_AI_PROVIDER):
        """
        初始化 AI 服务

        参数:
            provider: AI 提供商 ("moonshot", "zhipu", "gemini")
        """
        self.use_mock = USE_AI_MOCK
        self.provider = provider.lower()
        self.client = None

        if self.use_mock:
            logger.info(f"AIService initialized with MOCK mode (provider={provider})")
            return

        # 根据提供商初始化对应的客户端
        try:
            if self.provider == "gemini":
                if not GEMINI_API_KEY:
                    logger.warning("AIService: GEMINI_API_KEY not found")
                    return
                self.client = genai.Client(api_key=GEMINI_API_KEY)
                logger.info(f"AIService: Initialized Gemini Client (Model: {GEMINI_MODEL})")

            elif self.provider == "zhipu":
                if not ZHIPU_API_KEY:
                    logger.warning("AIService: ZHIPU_API_KEY not found")
                    return
                self.client = OpenAI(
                    api_key=ZHIPU_API_KEY,
                    base_url=ZHIPU_BASE_URL
                )
                logger.info(f"AIService: Initialized Zhipu Client (Model: {ZHIPU_MODEL})")

            else:  # 默认使用 Moonshot
                if not MOONSHOT_API_KEY:
                    logger.warning("AIService: MOONSHOT_API_KEY not found")
                    return
                self.client = OpenAI(
                    api_key=MOONSHOT_API_KEY,
                    base_url=MOONSHOT_BASE_URL
                )
                logger.info(f"AIService: Initialized Moonshot Client (Model: {MOONSHOT_MODEL})")

        except Exception as e:
            logger.error(f"AIService: Client initialization failed: {e}")

    def _get_model_name(self) -> str:
        """获取当前提供商的模型名称"""
        if self.provider == "gemini":
            return GEMINI_MODEL
        elif self.provider == "zhipu":
            return ZHIPU_MODEL
        else:  # moonshot
            return MOONSHOT_MODEL

    def _mock_query(self, text: str, context: Optional[str] = None) -> Dict:
        """
        Mock 查询方法：返回模拟的 AI 响应数据（用于调试）
        """
        text_trimmed = text.strip()
        word_count = len(text_trimmed.split())

        # 简单判断类型：根据文本长度和单词数量
        if word_count <= 1:
            query_type = "word"
            mock_data = {
                "type": "word",
                "content": {
                    "phonetic": f"/{text_trimmed.lower()}/",
                    "definition": f"{text_trimmed} 的中文释义（Mock数据）",
                    "explanation": f"这是关于 '{text_trimmed}' 的示例解释。在 Mock 模式下，这是模拟数据。"
                }
            }
        elif word_count <= 5:
            query_type = "phrase"
            mock_data = {
                "type": "phrase",
                "content": {
                    "phonetic": f"/{text_trimmed.lower().replace(' ', ' ')}/",
                    "definition": f"{text_trimmed} 的中文释义（Mock数据）",
                    "explanation": f"这是关于短语 '{text_trimmed}' 的示例解释。在 Mock 模式下，这是模拟数据。"
                }
            }
        else:
            query_type = "sentence"
            mock_data = {
                "type": "sentence",
                "content": {
                    "translation": f"这是句子 '{text_trimmed}' 的中文翻译（Mock数据）。",
                    "highlight_vocabulary": [
                        {"term": "example", "definition": "示例"}
                    ]
                }
            }

        logger.info(f"Mock AI 查询: type={query_type}, text={text[:30]}...")
        return mock_data

    def query(self, text: str, context: Optional[str] = None) -> Dict:
        """
        统一查询接口：传入划线文本，AI 自动判断是 word/phrase/sentence

        Args:
            text: 用户划线的文本
            context: 上下文（可选）

        Returns:
            dict: 解析后的 JSON 对象
        """
        if self.use_mock:
            return self._mock_query(text, context)

        if not self.client:
            raise ValueError(
                f"AI Client not initialized for provider '{self.provider}'. "
                "Please check your API keys configuration."
            )

        # 构建提示词 (Prompt)
        system_prompt = """# Role
你是一名专业的英语语言教学助手，擅长以简洁、准确的方式向英语学习者解释语言知识。

# Task
接收用户的输入内容，首先判断其属于"词汇 (word)"、"短语 (phrase)"还是"句子 (sentence)"，然后按照指定的 JSON 格式输出教学内容。

# Constraints
1. 输出必须严格遵守 JSON 格式，不要包含Markdown代码块标记（如 ```json）。直接输出 JSON 字符串。
2. 解释内容需简洁明了，适合英语学习者，总字数控制在 300 字以内。
3. 如果是专业术语，必须在解释中包含背景知识。

# Output Format (JSON)
{
    "type": "word | phrase | sentence",
    "content": {
        // 如果是 word 或 phrase：
        "phonetic": "...",
        "definition": "...",
        "explanation": "...",

        // 如果是 sentence：
        "translation": "...",
        "highlight_vocabulary": [
            {"term": "...", "definition": "..."}
        ]
    }
}"""

        if context:
            user_prompt = f"上下文：{context}\n\n查询内容：{text}"
        else:
            user_prompt = text

        try:
            target_model = self._get_model_name()
            response_text = ""
            executor = ThreadPoolExecutor(max_workers=1)

            def call_ai():
                if self.provider == "gemini":
                    # Gemini 原生调用
                    logger.debug(f"Calling Gemini ({target_model}) for text: {text[:20]}...")
                    full_prompt = f"{system_prompt}\n\nUser Query:\n{user_prompt}"
                    resp = self.client.models.generate_content(
                        model=target_model,
                        contents=full_prompt
                    )
                    return resp.text
                else:
                    # OpenAI 兼容调用 (Moonshot/Zhipu)
                    logger.debug(f"Calling {self.provider} ({target_model}) for text: {text[:20]}...")
                    completion = self.client.chat.completions.create(
                        model=target_model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=0.3,  # 保持低随机性
                    )
                    return completion.choices[0].message.content

            # 执行并等待
            try:
                future = executor.submit(call_ai)
                response_text = future.result(timeout=AI_QUERY_TIMEOUT)
            except FutureTimeoutError:
                logger.error(f"AI 查询超时: 超过 {AI_QUERY_TIMEOUT} 秒")
                raise TimeoutError("AI Request Timed Out")
            finally:
                executor.shutdown(wait=False)

            if not response_text:
                raise ValueError("AI Response is empty")

            # JSON 解析逻辑
            response_text = response_text.strip()
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()

            try:
                result = json.loads(response_text)
            except json.JSONDecodeError as e:
                logger.error(f"JSON Parsing Failed: {e}. Content: {response_text[:200]}")
                raise ValueError(f"Invalid JSON from AI") from e

            if "type" not in result or "content" not in result:
                raise ValueError("Missing 'type' or 'content' in AI response")

            return result

        except Exception as e:
            logger.error(f"AI Query Failed: {e}", exc_info=True)
            raise e
