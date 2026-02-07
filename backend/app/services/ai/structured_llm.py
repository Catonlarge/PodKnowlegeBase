"""
Structured LLM Module

This module provides a unified interface for structured output across different AI providers.
It uses the adapter pattern to support multiple providers with different structured output methods.

Design Principles:
    - All providers use their preferred method (native or json_mode)
    - No prompt_only fallback - rely on validation + retry + degradation
    - Pydantic validation failures raise exceptions for upstream retry logic
"""
from typing import Any, TypeVar
from pydantic import BaseModel

from .providers import get_provider_adapter
from .structured_output_config import get_provider_config


T = TypeVar('T', bound=BaseModel)


class StructuredLLM:
    """
    Unified structured output LLM wrapper.

    This class provides a consistent interface for getting structured outputs
    from different AI providers. It automatically selects the appropriate method
    (native or json_mode) based on the provider's capabilities.

    Architecture:
        - Uses adapter pattern for provider extensibility
        - Each provider has its own adapter with specific logic
        - Validation failures raise exceptions for upstream @ai_retry

    Examples:
        >>> llm = StructuredLLM(
        ...     provider="moonshot",
        ...     model="kimi-k2-0905-preview",
        ...     api_key="sk-xxx",
        ...     base_url="https://api.moonshot.cn/v1"
        ... )
        >>> structured_llm = llm.with_structured_output(ProofreadingResponse)
        >>> result = structured_llm.invoke(messages)
    """

    def __init__(self, provider: str, model: str, **kwargs):
        """
        Initialize the StructuredLLM.

        Args:
            provider: Provider name (moonshot, kimi, zhipu, gemini)
            model: Model name/identifier
            **kwargs: Provider-specific parameters:
                - api_key: API key for the provider
                - base_url: Base URL for OpenAI-compatible providers
                - temperature: Sampling temperature (default: 0.7)
        """
        self.provider = provider.lower()
        self.model = model
        self.config = get_provider_config(provider)

        # Create provider adapter using factory method
        self.adapter = get_provider_adapter(provider, model, **kwargs)

    def with_structured_output(
        self,
        schema: type[T],
        method: str = "auto"
    ) -> Any:
        """
        Get an LLM with structured output support.

        Args:
            schema: Pydantic model class for validation
            method:
                - "auto": Automatically select best method (recommended)
                - "native": Force native structured output (Gemini only)
                - "json_mode": Force JSON mode (Kimi/Zhipu)

        Returns:
            StructuredLLMWrapper that can be invoked with messages

        Raises:
            ValueError: If method is not supported by the provider

        Examples:
            >>> llm = StructuredLLM(provider="moonshot", model="kimi-k2", api_key="sk-xxx")
            >>> structured_llm = llm.with_structured_output(ProofreadingResponse)
            >>> result = structured_llm.invoke([SystemMessage(content="..."), HumanMessage(content="...")])
        """
        if method == "auto":
            method = self.config.preferred_method

        # Validate method is supported
        if method == "native" and not self.config.supports_native:
            raise ValueError(
                f"Provider '{self.provider}' does not support native structured output. "
                f"Use method='json_mode' instead."
            )
        if method == "json_mode" and not self.config.supports_json_mode:
            raise ValueError(
                f"Provider '{self.provider}' does not support JSON mode. "
                f"Use method='native' instead."
            )

        return StructuredLLMWrapper(self.adapter, schema)


class StructuredLLMWrapper:
    """
    Wrapper for structured output LLM instances.

    This class wraps the provider adapter and provides a consistent
    invoke interface for all providers.
    """

    def __init__(self, adapter, schema: type[T]):
        """
        Initialize the wrapper.

        Args:
            adapter: Provider adapter instance
            schema: Pydantic model class for validation
        """
        self.adapter = adapter
        self.schema = schema

    def invoke(self, messages, **kwargs) -> T:
        """
        Invoke the LLM with structured output.

        Args:
            messages: Chat messages (list of BaseMessage)
            **kwargs: Additional parameters for the provider

        Returns:
            Validated Pydantic model instance

        Raises:
            ValueError: If API call fails or validation fails
                        (This exception is caught by @ai_retry decorator)

        Examples:
            >>> wrapper.invoke([
            ...     SystemMessage(content="You are a subtitle proofreader"),
            ...     HumanMessage(content="Check these subtitles...")
            ... ])
        """
        return self.adapter.create_completion(messages, self.schema, **kwargs)

    def bind(self, **kwargs):
        """
        Bind parameters for future invocations.

        Args:
            **kwargs: Parameters to bind

        Returns:
            Self for chaining
        """
        # For compatibility with LangChain patterns
        return self


__all__ = [
    "StructuredLLM",
    "StructuredLLMWrapper",
]
