"""
AI Retry Decorator Module

This module provides a retry decorator for AI API calls with exponential backoff.
It handles transient failures and validation errors by automatically retrying with delays.

Design Principles:
    - Exponential backoff: delay = initial_delay * (backoff_factor ^ attempt)
    - Configurable max retries and delays
    - Structured logging for debugging
    - Raises last exception after all retries exhausted
"""
import time
from functools import wraps
from typing import Type, Tuple, Callable, Any
from loguru import logger


def ai_retry(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    retry_on: Tuple[Type[Exception], ...] = (Exception,)
) -> Callable:
    """
    Decorator for retrying AI calls with exponential backoff.

    Use this decorator on AI service methods to handle:
    - Network errors
    - API rate limits
    - Pydantic validation failures
    - Transient failures

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        initial_delay: Initial delay in seconds before first retry (default: 1.0)
        backoff_factor: Multiplier for delay after each retry (default: 2.0)
        retry_on: Tuple of exception types to retry on (default: all Exceptions)

    Returns:
        Decorated function that retries on failure

    Examples:
        >>> @ai_retry(max_retries=2, initial_delay=0.5)
        >>> def call_ai_service(prompt):
        ...     return llm.invoke(prompt)
        >>>
        >>> # Retries with delays: 0.5s, 1.0s (if max_retries=2)
        >>> result = call_ai_service("Hello")
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            delay = initial_delay
            last_exception = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except retry_on as e:
                    last_exception = e

                    if attempt < max_retries - 1:
                        logger.warning(
                            f"{func.__name__} 失败 (尝试 {attempt + 1}/{max_retries}): {e}, "
                            f"{delay:.1f}秒后重试..."
                        )
                        time.sleep(delay)
                        delay *= backoff_factor
                    else:
                        logger.error(
                            f"{func.__name__} 重试 {max_retries} 次后仍失败"
                        )

            # All retries exhausted, raise the last exception
            if last_exception:
                raise last_exception
            return None

        return wrapper
    return decorator


def get_retry_config(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0
) -> dict:
    """
    Get retry configuration as a dictionary.

    Useful for passing retry config to services.

    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        backoff_factor: Multiplier for delay after each retry

    Returns:
        Dictionary with retry configuration

    Examples:
        >>> config = get_retry_config(max_retries=2)
        >>> service = ProofreadingService(db, retry_config=config)
    """
    return {
        "max_retries": max_retries,
        "initial_delay": initial_delay,
        "backoff_factor": backoff_factor,
    }


__all__ = [
    "ai_retry",
    "get_retry_config",
]
