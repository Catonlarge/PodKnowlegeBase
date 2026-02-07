"""
Moonshot (Kimi) Provider Adapter

This module implements the adapter for Moonshot Kimi API.
Kimi supports JSON mode via response_format parameter but not native structured output.
"""
from typing import Type
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage

from .base_provider import BaseProviderAdapter, T


class MoonshotProviderAdapter(BaseProviderAdapter):
    """
    Moonshot (Kimi) provider adapter.

    Method: JSON Mode
    - Uses response_format={"type": "json_object"}
    - Validates response with Pydantic
    - Does NOT support native with_structured_output()

    Reference: https://platform.moonshot.cn/docs/intro
    """

    def _initialize_client(self, **kwargs):
        """Initialize Kimi (Moonshot) OpenAI-compatible client."""
        self.client = ChatOpenAI(
            model=self.model,
            base_url=kwargs.get("base_url"),
            api_key=kwargs.get("api_key"),
            temperature=kwargs.get("temperature", 0.7),
        )

    def get_method_type(self) -> str:
        """Return method type: json_mode."""
        return "json_mode"

    def create_completion(self, messages: list[BaseMessage], schema: type[T], **kwargs) -> T:
        """
        Create completion with JSON mode.

        Args:
            messages: Chat messages
            schema: Pydantic model for validation
            **kwargs: Additional parameters

        Returns:
            Validated Pydantic model instance

        Raises:
            ValueError: If API call fails or validation fails
        """
        try:
            # Use response_format to force JSON output
            response = self.client.invoke(
                messages,
                response_format={"type": "json_object"},
                **kwargs
            )

            # Validate with Pydantic
            return self.validate_response(response.content, schema)

        except Exception as e:
            raise ValueError(f"Moonshot API call failed: {e}") from e
