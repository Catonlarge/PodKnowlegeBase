"""
Provider Adapters Module

This module provides a unified interface for different AI providers through adapter pattern.
New providers can be easily added by:
1. Creating a new adapter class inheriting from BaseProviderAdapter
2. Registering it with register_provider()
3. Updating PROVIDER_CONFIGS in config/structured_output.py

Architecture:
    - Adapter Pattern: Each provider has its own adapter
    - Factory Pattern: get_provider_adapter() creates adapter instances
    - Registry Pattern: PROVIDER_REGISTRY enables dynamic extension
"""
from typing import Dict, Type

from .base_provider import BaseProviderAdapter
from .moonshot_provider import MoonshotProviderAdapter
from .zhipu_provider import ZhipuProviderAdapter
from .gemini_provider import GeminiProviderAdapter


# Provider registry - supports dynamic extension
PROVIDER_REGISTRY: Dict[str, Type[BaseProviderAdapter]] = {
    "moonshot": MoonshotProviderAdapter,
    "kimi": MoonshotProviderAdapter,  # Alias for Moonshot
    "zhipu": ZhipuProviderAdapter,
    "gemini": GeminiProviderAdapter,
}


def register_provider(name: str, adapter_class: Type[BaseProviderAdapter]):
    """
    Register a new provider adapter.

    Args:
        name: Provider name (lowercase)
        adapter_class: Adapter class inheriting from BaseProviderAdapter

    Examples:
        >>> from app.services.ai.providers import register_provider
        >>> from .deepseek_provider import DeepSeekProviderAdapter
        >>> register_provider("deepseek", DeepSeekProviderAdapter)

    Note:
        After registering a new provider, also update:
        - PROVIDER_CONFIGS in config/structured_output.py
        - Add API key to app/config.py
    """
    PROVIDER_REGISTRY[name.lower()] = adapter_class


def get_provider_adapter(provider: str, model: str, **kwargs) -> BaseProviderAdapter:
    """
    Get a provider adapter instance.

    Args:
        provider: Provider name (case-insensitive)
        model: Model name/identifier
        **kwargs: Provider-specific parameters (api_key, base_url, etc.)

    Returns:
        BaseProviderAdapter: Provider adapter instance

    Raises:
        ValueError: If provider is not registered

    Examples:
        >>> adapter = get_provider_adapter(
        ...     "moonshot",
        ...     model="kimi-k2-0905-preview",
        ...     api_key="sk-xxx",
        ...     base_url="https://api.moonshot.cn/v1"
        ... )
        >>> result = adapter.create_completion(messages, ProofreadingResponse)
    """
    provider = provider.lower()
    if provider not in PROVIDER_REGISTRY:
        available = list(PROVIDER_REGISTRY.keys())
        raise ValueError(
            f"Unknown provider: {provider}. "
            f"Available providers: {available}"
        )

    adapter_class = PROVIDER_REGISTRY[provider]
    return adapter_class(model=model, **kwargs)


def list_providers() -> list[str]:
    """
    List all registered providers.

    Returns:
        List of provider names
    """
    return list(PROVIDER_REGISTRY.keys())


__all__ = [
    "BaseProviderAdapter",
    "MoonshotProviderAdapter",
    "ZhipuProviderAdapter",
    "GeminiProviderAdapter",
    "register_provider",
    "get_provider_adapter",
    "list_providers",
]
