"""
Provider Structured Output Configuration Module

This module defines the configuration for different AI providers' structured output capabilities.
Each provider has different support for structured output methods:
- moonshot/kimi: Supports JSON mode via response_format parameter
- zhipu: Supports JSON mode via response_format parameter
- gemini: Supports native structured output via with_structured_output

Architecture:
    - No prompt_only fallback - rely on validation + retry + degradation strategy
    - JSON mode providers use response_format={"type": "json_object"}
    - Native providers use with_structured_output() method
"""
from dataclasses import dataclass
from typing import Literal, Dict


@dataclass(frozen=True)
class ProviderStructuredOutputConfig:
    """
    Configuration for a provider's structured output capabilities.

    Attributes:
        provider: Provider name (moonshot, kimi, zhipu, gemini)
        supports_native: Whether provider supports native structured output
        supports_json_mode: Whether provider supports JSON mode
        preferred_method: Preferred method for structured output
    """
    provider: str
    supports_native: bool
    supports_json_mode: bool
    preferred_method: Literal["native", "json_mode"]


# Provider configurations
PROVIDER_CONFIGS: Dict[str, ProviderStructuredOutputConfig] = {
    "moonshot": ProviderStructuredOutputConfig(
        provider="moonshot",
        supports_native=False,
        supports_json_mode=True,
        preferred_method="json_mode",
    ),
    "kimi": ProviderStructuredOutputConfig(
        provider="kimi",
        supports_native=False,
        supports_json_mode=True,
        preferred_method="json_mode",
    ),
    "zhipu": ProviderStructuredOutputConfig(
        provider="zhipu",
        supports_native=False,
        supports_json_mode=True,
        preferred_method="json_mode",
    ),
    "gemini": ProviderStructuredOutputConfig(
        provider="gemini",
        supports_native=True,
        supports_json_mode=False,
        preferred_method="native",
    ),
}


def get_provider_config(provider: str) -> ProviderStructuredOutputConfig:
    """
    Get configuration for a specific provider.

    Args:
        provider: Provider name (case-insensitive)

    Returns:
        ProviderStructuredOutputConfig: Provider configuration

    Raises:
        ValueError: If provider is not supported

    Examples:
        >>> config = get_provider_config("moonshot")
        >>> config.preferred_method
        'json_mode'
        >>> config = get_provider_config("gemini")
        >>> config.preferred_method
        'native'
    """
    provider = provider.lower()
    if provider not in PROVIDER_CONFIGS:
        supported = list(PROVIDER_CONFIGS.keys())
        raise ValueError(
            f"Unknown provider: {provider}. "
            f"Supported providers: {supported}"
        )
    return PROVIDER_CONFIGS[provider]


def list_supported_providers() -> list[str]:
    """
    List all supported providers.

    Returns:
        List of provider names
    """
    return list(PROVIDER_CONFIGS.keys())
