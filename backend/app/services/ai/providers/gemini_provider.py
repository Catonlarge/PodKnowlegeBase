"""
Gemini Provider Adapter

This module implements the adapter for Google Gemini API.
Gemini supports native structured output via with_structured_output().
"""
from typing import Type
from pydantic import BaseModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import BaseMessage

from .base_provider import BaseProviderAdapter, T


class GeminiProviderAdapter(BaseProviderAdapter):
    """
    Gemini provider adapter.

    Method: Native Structured Output
    - Uses with_structured_output() method
    - No need for response_format parameter
    - Automatic validation by LangChain

    Reference: https://python.langchain.com/docs/integrations/platforms/google_ai
    """

    def _initialize_client(self, **kwargs):
        """Initialize Gemini client."""
        try:
            self.client = ChatGoogleGenerativeAI(
                model=self.model,
                api_key=kwargs.get("api_key"),
                temperature=kwargs.get("temperature", 0.7),
            )
        except ImportError as e:
            raise ImportError(
                "langchain-google-genai is required for Gemini provider. "
                "Install it with: pip install langchain-google-genai"
            ) from e

    def get_method_type(self) -> str:
        """Return method type: native."""
        return "native"

    def create_completion(self, messages: list[BaseMessage], schema: type[T], **kwargs) -> T:
        """
        Create completion with native structured output.

        Args:
            messages: Chat messages
            schema: Pydantic model for validation
            **kwargs: Additional parameters

        Returns:
            Validated Pydantic model instance

        Raises:
            ValueError: If API call fails
        """
        try:
            # Use native structured output
            structured_llm = self.client.with_structured_output(schema)
            return structured_llm.invoke(messages, **kwargs)

        except Exception as e:
            raise ValueError(f"Gemini API call failed: {e}") from e
