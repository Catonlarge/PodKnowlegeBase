"""
Base Provider Adapter Module

This module defines the abstract base class for all provider adapters.
Provider adapters encapsulate the differences between AI providers' structured output methods.
"""
from abc import ABC, abstractmethod
from typing import TypeVar
from pydantic import BaseModel


T = TypeVar('T', bound=BaseModel)


class BaseProviderAdapter(ABC):
    """
    Abstract base class for provider adapters.

    Each provider adapter implements the specific logic for:
    - Initializing the provider's client
    - Determining the method type (native or json_mode)
    - Creating completion requests with structured output

    Design Pattern: Adapter Pattern
    - Allows different providers to be used interchangeably
    - Encapsulates provider-specific logic
    - Enables easy extension for new providers
    """

    def __init__(self, model: str, **kwargs):
        """
        Initialize the provider adapter.

        Args:
            model: Model name/identifier
            **kwargs: Additional provider-specific parameters
        """
        self.model = model
        self._initialize_client(**kwargs)

    @abstractmethod
    def _initialize_client(self, **kwargs):
        """
        Initialize the provider's client.

        Args:
            **kwargs: Provider-specific parameters (api_key, base_url, etc.)
        """
        pass

    @abstractmethod
    def get_method_type(self) -> str:
        """
        Return the structured output method type.

        Returns:
            "native" for providers with native structured output (Gemini)
            "json_mode" for providers using JSON mode (Kimi, Zhipu)
        """
        pass

    @abstractmethod
    def create_completion(self, messages, schema: type[T], **kwargs) -> T:
        """
        Create a completion request with structured output.

        Args:
            messages: Chat messages
            schema: Pydantic model class for validation
            **kwargs: Additional parameters for the completion

        Returns:
            Validated instance of the schema model

        Raises:
            ValueError: If response validation fails
        """
        pass

    def validate_response(self, response_content: str, schema: type[T]) -> T:
        """
        Generic response validation using Pydantic.

        Args:
            response_content: Raw JSON string from provider
            schema: Pydantic model class for validation

        Returns:
            Validated instance of the schema model

        Raises:
            ValueError: If JSON parsing or validation fails
        """
        try:
            return schema.model_validate_json(response_content)
        except Exception as e:
            raise ValueError(
                f"Failed to validate JSON against schema: {e}\n"
                f"Raw content: {response_content[:500]}"
            ) from e
